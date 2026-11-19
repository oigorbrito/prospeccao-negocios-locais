"""Passo 3: adaptador. Lê os leads do OSM, descarta quem não pode ser contatado,
gera o site de demonstração de cada um e grava o CSV final com link e telefone.

Uso:
  python3 ponte.py --entrada dados/leads_osm.csv --saida dados/leads_finais.csv --sites sites --limite 10
"""
import argparse
import csv
from pathlib import Path

import config
from gerador_sites import gerar_arquivo

COLUNAS_FINAIS = ["osm_id", "nome", "categoria", "bairro", "telefone", "telefone_normalizado",
                  "whatsapp_provavel", "slug", "link_site", "precisa_conferir_site", "status"]


def preparar(entrada, bloqueados, limite=None):
    """Devolve (aceitos, descartados) com o motivo de cada descarte."""
    aceitos, descartados = [], []
    with open(entrada, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            numero = "".join(ch for ch in (linha.get("telefone_normalizado") or "") if ch.isdigit())
            if not numero:
                descartados.append((linha.get("nome"), "sem telefone válido"))
            elif numero in bloqueados:
                descartados.append((linha.get("nome"), "na lista de bloqueio"))
            elif linha.get("website") or linha.get("site"):
                descartados.append((linha.get("nome"), "já tem site"))
            else:
                aceitos.append(linha)
    if limite:
        aceitos = aceitos[:limite]
    return aceitos, descartados


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", default="dados/leads_osm.csv")
    ap.add_argument("--saida", default="dados/leads_finais.csv")
    ap.add_argument("--sites", default="sites")
    ap.add_argument("--bloqueados", default="dados/bloqueados.csv")
    ap.add_argument("--limite", type=int, default=0, help="gerar só os N primeiros (bom para teste)")
    a = ap.parse_args(argv)

    cfg = config.carregar()
    bloqueados = config.carregar_bloqueados(a.bloqueados)
    aceitos, descartados = preparar(a.entrada, bloqueados, a.limite or None)

    base = (cfg["SITE_BASE_URL"] or "").rstrip("/")
    cfg_site = {"estudio": cfg["ESTUDIO"]}
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    with open(a.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_FINAIS)
        w.writeheader()
        for lead in aceitos:
            slug = gerar_arquivo(lead, cfg_site, a.sites)
            link = f"{base}/{slug}/" if base else ""
            w.writerow({
                "osm_id": lead.get("osm_id", ""), "nome": lead.get("nome", ""),
                "categoria": lead.get("categoria", ""), "bairro": lead.get("bairro", ""),
                "telefone": lead.get("telefone", ""), "telefone_normalizado": lead.get("telefone_normalizado", ""),
                "whatsapp_provavel": lead.get("whatsapp_provavel", ""), "slug": slug, "link_site": link,
                "precisa_conferir_site": "sim",
                "status": "site_pronto" if link else "site_gerado_sem_link_publicado",
            })
    print(f"{len(aceitos)} sites gerados em {a.sites}/ ; lista final: {a.saida}")
    for nome, motivo in descartados:
        print(f"  descartado: {nome} ({motivo})")
    if not base:
        print("Atenção: SITE_BASE_URL está vazio. Os links ainda não existem publicamente, e a fila não aceita mensagem sem link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
