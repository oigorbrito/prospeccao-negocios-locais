"""Testes offline do pipeline. Usam dados fictícios e não acessam a internet.

Rodar, a partir da pasta pipeline/:
  python3 -m unittest discover -s tests -v
"""
import csv
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PASTA))

import captar_osm  # noqa: E402
import config  # noqa: E402
import fila_whatsapp as fw  # noqa: E402
import gerador_sites as gs  # noqa: E402
import horarios  # noqa: E402
import ponte  # noqa: E402

CFG = {"ESTUDIO": "Estúdio Teste", "LIMITE_DIARIO": 25}
PALAVRAS_PROIBIDAS = ["avalia", "depoimento", "prêmio", "premiado", "estrelas", "satisfeit", "anos de experiência",
                      "garantia", "melhor da cidade", "líder"]


def lead_fake(**extra):
    base = {"nome": "Padaria Exemplo", "categoria": "shop=bakery", "bairro": "Bairro Teste", "cidade": "Porto Alegre",
            "telefone": "(51) 90000-0001", "telefone_normalizado": "5551900000001", "endereco": "Rua Fictícia, 10",
            "lat": "-30.02", "lon": "-51.20", "opening_hours": "Mo-Fr 07:00-19:00; Sa 07:00-13:00; Su off",
            "slug": "padaria-exemplo-1", "link_site": "https://exemplo.test/padaria-exemplo-1/"}
    base.update(extra)
    return base


class TelefoneTest(unittest.TestCase):
    def test_celular_com_nove(self):
        self.assertEqual(captar_osm.normalizar_telefone("+55 51 99123-4567"), ("5551991234567", True))

    def test_fixo(self):
        self.assertEqual(captar_osm.normalizar_telefone("+55 51 3333-4444"), ("555133334444", False))

    def test_varios_separados_pega_o_primeiro(self):
        self.assertEqual(captar_osm.normalizar_telefone("51 3333-4444; 51 99999-0000")[0], "555133334444")

    def test_invalido(self):
        self.assertEqual(captar_osm.normalizar_telefone("123"), ("", False))
        self.assertEqual(captar_osm.normalizar_telefone(""), ("", False))


class CaptarTest(unittest.TestCase):
    def test_consulta_usa_ponto_e_raio(self):
        q = captar_osm.montar_consulta(-30.0, -51.2, 1500)
        self.assertIn("around:1500,-30.0,-51.2", q)
        self.assertIn('"amenity"', q)

    def test_filtra_site_marcado_sem_telefone_e_lixo(self):
        com_site = {"type": "node", "id": 1, "lat": 1, "lon": 1,
                    "tags": {"name": "A", "shop": "bakery", "phone": "51 3333-4444", "website": "https://a.test"}}
        sem_fone = {"type": "node", "id": 2, "lat": 1, "lon": 1, "tags": {"name": "B", "shop": "bakery"}}
        banco = {"type": "node", "id": 3, "lat": 1, "lon": 1,
                 "tags": {"name": "Caixa", "amenity": "atm", "phone": "51 3333-4444"}}
        ok = {"type": "node", "id": 4, "lat": -30, "lon": -51, "tags": {"name": "C", "shop": "hairdresser",
                                                                         "phone": "51 99999-0000"}}
        self.assertIsNone(captar_osm.elemento_para_lead(com_site))
        self.assertIsNone(captar_osm.elemento_para_lead(sem_fone))
        self.assertIsNone(captar_osm.elemento_para_lead(banco))
        lead = captar_osm.elemento_para_lead(ok)
        self.assertEqual(lead["osm_id"], "node4")
        self.assertEqual(lead["whatsapp_provavel"], "sim")
        self.assertEqual(lead["verificar_site"], "sim")


class HorarioTest(unittest.TestCase):
    def test_semana_com_fechado(self):
        h = horarios.parse("Mo-Fr 09:00-18:00; Sa 09:00-12:00; Su off")
        self.assertEqual(h["texto"][0], ("Segunda", "09:00–18:00"))
        self.assertEqual(h["texto"][5], ("Sábado", "09:00–12:00"))
        self.assertEqual(h["texto"][6], ("Domingo", "Fechado"))
        self.assertEqual(h["faixas"][6], [])

    def test_24_horas(self):
        self.assertEqual(horarios.parse("24/7")["faixas"][3], [[0, 1440]])

    def test_formato_nao_entendido_devolve_none(self):
        self.assertIsNone(horarios.parse("Mo-Fr 09:00-18:00 PH off, Dec 24 off"))
        self.assertIsNone(horarios.parse(""))


class SiteTest(unittest.TestCase):
    def test_nao_inventa_texto_de_marketing(self):
        html = gs.renderizar(lead_fake(), CFG).lower()
        for palavra in PALAVRAS_PROIBIDAS:
            self.assertNotIn(palavra, html, f"texto inventado encontrado: {palavra}")

    def test_mostra_dados_reais(self):
        html = gs.renderizar(lead_fake(), CFG)
        self.assertIn("Padaria Exemplo", html)
        self.assertIn("Rua Fictícia, 10", html)
        self.assertIn("https://wa.me/5551900000001", html)
        self.assertIn("07:00–19:00", html)

    def test_escapa_html_do_nome(self):
        html = gs.renderizar(lead_fake(nome="<script>x</script>"), CFG)
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_aviso_de_demonstracao_so_sem_final(self):
        self.assertIn("Não é o site oficial", gs.renderizar(lead_fake(), CFG))
        self.assertNotIn("Não é o site oficial", gs.renderizar(lead_fake(), CFG, final=True))

    def test_sem_horario_nao_inventa(self):
        html = gs.renderizar(lead_fake(opening_hours=""), CFG)
        self.assertIn("Horário não informado", html)

    def test_ramo_por_categoria(self):
        self.assertEqual(gs.ramo_de("amenity=restaurant"), "alimentacao")
        self.assertEqual(gs.ramo_de("shop=hairdresser"), "beleza")
        self.assertEqual(gs.ramo_de("office=lawyer"), "geral")


class PonteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.entrada = self.tmp / "osm.csv"
        linhas = [
            {"osm_id": "n1", "nome": "Com fone", "categoria": "shop=bakery", "telefone": "51 99999-0001",
             "telefone_normalizado": "5551999990001", "whatsapp_provavel": "sim", "endereco": "", "bairro": "",
             "cidade": "Porto Alegre", "lat": "", "lon": "", "opening_hours": "", "verificar_site": "sim"},
            {"osm_id": "n2", "nome": "Bloqueado", "categoria": "shop=bakery", "telefone": "51 99999-0002",
             "telefone_normalizado": "5551999990002", "whatsapp_provavel": "sim", "endereco": "", "bairro": "",
             "cidade": "", "lat": "", "lon": "", "opening_hours": "", "verificar_site": "sim"},
            {"osm_id": "n3", "nome": "Sem fone", "categoria": "shop=bakery", "telefone": "",
             "telefone_normalizado": "", "whatsapp_provavel": "nao", "endereco": "", "bairro": "",
             "cidade": "", "lat": "", "lon": "", "opening_hours": "", "verificar_site": "sim"},
        ]
        with open(self.entrada, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)

    def test_descarta_bloqueado_e_sem_telefone(self):
        aceitos, descartados = ponte.preparar(self.entrada, {"5551999990002"})
        self.assertEqual([a["nome"] for a in aceitos], ["Com fone"])
        motivos = {n: m for n, m in descartados}
        self.assertEqual(motivos["Bloqueado"], "na lista de bloqueio")
        self.assertEqual(motivos["Sem fone"], "sem telefone válido")

    def test_ponta_a_ponta_sem_base_url_nao_cria_link(self):
        saida = self.tmp / "finais.csv"
        cfg_env = self.tmp / ".env"
        cfg_env.write_text("ESTUDIO=Estúdio Teste\nSITE_BASE_URL=\n", encoding="utf-8")
        ponte_cfg_original = config.carregar
        config.carregar = lambda *a, **k: ponte_cfg_original(cfg_env)
        try:
            ponte.main(["--entrada", str(self.entrada), "--saida", str(saida), "--sites", str(self.tmp / "sites"),
                        "--bloqueados", str(self.tmp / "nao_existe.csv")])
        finally:
            config.carregar = ponte_cfg_original
        with open(saida, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 2)
        self.assertTrue(all(l["link_site"] == "" for l in linhas))
        self.assertTrue(all(l["status"] == "site_gerado_sem_link_publicado" for l in linhas))
        self.assertTrue((self.tmp / "sites" / linhas[0]["slug"] / "index.html").exists())


class FilaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fila = self.tmp / "fila.csv"
        self.bloq = self.tmp / "bloq.csv"
        self.finais = self.tmp / "finais.csv"
        campos = ["osm_id", "nome", "telefone_normalizado", "slug", "link_site"]
        with open(self.finais, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerow({"osm_id": "n1", "nome": "Ana", "telefone_normalizado": "5551999990001",
                        "slug": "ana", "link_site": "https://exemplo.test/ana/"})
            w.writerow({"osm_id": "n2", "nome": "Beto", "telefone_normalizado": "5551999990002",
                        "slug": "beto", "link_site": "https://exemplo.test/beto/"})
            w.writerow({"osm_id": "n3", "nome": "Sem link", "telefone_normalizado": "5551999990003",
                        "slug": "sem", "link_site": ""})
        self.cfg = {"ESTUDIO": "Estúdio Teste", "LIMITE_DIARIO": 25}

    def test_gerar_so_com_link_e_sem_bloqueado(self):
        fw.gerar(self.finais, self.fila, {"5551999990002"}, self.cfg, hoje="2026-11-19T10:00")
        linhas = fw.ler(self.fila)
        self.assertEqual([l["nome"] for l in linhas], ["Ana"])
        self.assertEqual(linhas[0]["status"], "aguardando_aprovacao")
        self.assertIn("SAIR", linhas[0]["mensagem"])
        self.assertIn("https://exemplo.test/ana/", linhas[0]["mensagem"])

    def test_gerar_nao_duplica(self):
        fw.gerar(self.finais, self.fila, set(), self.cfg)
        novos, _ = fw.gerar(self.finais, self.fila, set(), self.cfg)
        self.assertEqual(novos, 0)
        self.assertEqual(len(fw.ler(self.fila)), 2)

    def test_link_so_depois_de_aprovar(self):
        fw.gerar(self.finais, self.fila, set(), self.cfg)
        linhas = fw.ler(self.fila)
        with self.assertRaises(SystemExit):
            fw.link_envio(linhas, "1", set(), self.cfg)
        fw.aprovar(linhas, "1", hoje="2026-11-19T10:05")
        url = fw.link_envio(linhas, "1", set(), self.cfg)
        self.assertTrue(url.startswith("https://wa.me/5551999990001?text="))
        self.assertIn("SAIR", urllib.parse.unquote(url))

    def test_limite_diario(self):
        cfg = {"ESTUDIO": "x", "LIMITE_DIARIO": 20}
        linhas = [{"id": str(i), "status": "enviada", "enviado_em": "2026-11-19T09:00", "telefone_normalizado": str(i),
                   "link_site": "x", "mensagem": "m", "nome": "n", "slug": "s", "criado_em": "", "aprovado_em": "",
                   } for i in range(20)]
        linhas.append({"id": "99", "status": "aprovada", "enviado_em": "", "telefone_normalizado": "5599",
                       "link_site": "x", "mensagem": "m", "nome": "n", "slug": "s", "criado_em": "", "aprovado_em": ""})
        with self.assertRaises(SystemExit):
            fw.link_envio(linhas, "99", set(), cfg, hoje="2026-11-19")

    def test_bloquear_marca_e_impede(self):
        fw.gerar(self.finais, self.fila, set(), self.cfg)
        fw.bloquear(self.bloq, fw.ler(self.fila), self.fila, "(51) 99999-0001")
        linhas = fw.ler(self.fila)
        self.assertEqual(linhas[0]["status"], "bloqueado")
        self.assertIn("5551999990001", config.carregar_bloqueados(self.bloq))

    def test_revisar_aprova_e_rejeita(self):
        fw.gerar(self.finais, self.fila, set(), self.cfg)
        fw.gerar(self.finais, self.fila, set(), self.cfg)  # não duplica
        respostas = iter(["a", "r"])  # aprova Ana, rejeita Beto
        fw.revisar(self.fila, entrada=lambda _p="": next(respostas), saida=lambda *_: None)
        linhas = {l["nome"]: l["status"] for l in fw.ler(self.fila)}
        self.assertEqual(linhas, {"Ana": "aprovada", "Beto": "rejeitada"})

    def test_limite_fora_da_faixa_recusado(self):
        env = self.tmp / "e.env"
        env.write_text("LIMITE_DIARIO=50\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            config.carregar(env)


if __name__ == "__main__":
    unittest.main()
