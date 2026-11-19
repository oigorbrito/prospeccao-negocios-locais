"""Passo 4: fila de mensagens de WhatsApp com aprovação humana.

REGRAS EMBUTIDAS NO CÓDIGO
- Este script NÃO envia nada. Ele só prepara o texto e gera um link wa.me que você abre e envia manualmente.
- Mensagem só vira link depois de aprovada por você, uma a uma (comando revisar, ou aprovar ID).
- Mensagem nunca é gerada sem link público do site.
- Quem está na lista de bloqueio nunca entra na fila nem recebe link.
- Limite diário (LIMITE_DIARIO, entre 20 e 30) conta as mensagens marcadas como enviadas no dia.

Comandos:
  python3 fila_whatsapp.py gerar                 # cria a fila a partir de dados/leads_finais.csv
  python3 fila_whatsapp.py listar                # mostra a fila
  python3 fila_whatsapp.py revisar               # aprova/rejeita uma a uma
  python3 fila_whatsapp.py link ID               # mostra o link wa.me de uma mensagem aprovada
  python3 fila_whatsapp.py marcar-enviada ID     # depois que você enviou manualmente
  python3 fila_whatsapp.py bloquear TELEFONE     # pediu para sair: nunca mais recebe mensagem
"""
import argparse
import csv
import sys
import urllib.parse
from datetime import date, datetime
from pathlib import Path

import captar_osm
import config

COLUNAS_FILA = ["id", "telefone_normalizado", "nome", "slug", "link_site", "mensagem", "status",
                "criado_em", "aprovado_em", "enviado_em"]
STATUS = ("aguardando_aprovacao", "aprovada", "rejeitada", "enviada", "bloqueado")


def texto_mensagem(nome, link, estudio):
    """Mensagem em português do Brasil. Não afirma nada sobre o negócio além do nome e do link."""
    quem = estudio or "um estúdio de sites"
    return (f"Olá, tudo bem? Aqui é do {quem}. Montamos uma página de demonstração gratuita para o {nome}: {link}\n\n"
            f"É só um exemplo, sem nenhum compromisso. Se não quiser receber mensagens nossas, "
            f"responda SAIR que não entramos em contato de novo.")


def ler(caminho):
    p = Path(caminho)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def salvar(caminho, linhas):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_FILA)
        w.writeheader()
        for linha in linhas:
            w.writerow({c: linha.get(c, "") for c in COLUNAS_FILA})


def gerar(finais, fila, bloqueados, cfg, hoje=None):
    """Acrescenta à fila os leads com link. Não mexe em mensagens já existentes."""
    hoje = hoje or datetime.now().isoformat(timespec="minutes")
    linhas = ler(fila)
    ja = {r["telefone_normalizado"] for r in linhas}
    proximo = max([int(r["id"]) for r in linhas] or [0]) + 1
    novos, pulados = 0, []
    for lead in ler(finais):
        numero = lead.get("telefone_normalizado", "")
        if not lead.get("link_site"):
            pulados.append((lead.get("nome"), "sem link publicado"))
            continue
        if numero in bloqueados:
            pulados.append((lead.get("nome"), "na lista de bloqueio"))
            continue
        if numero in ja:
            continue
        linhas.append({
            "id": proximo, "telefone_normalizado": numero, "nome": lead.get("nome", ""),
            "slug": lead.get("slug", ""), "link_site": lead["link_site"],
            "mensagem": texto_mensagem(lead.get("nome", ""), lead["link_site"], cfg.get("ESTUDIO", "")),
            "status": "aguardando_aprovacao", "criado_em": hoje, "aprovado_em": "", "enviado_em": "",
        })
        ja.add(numero)
        proximo += 1
        novos += 1
    salvar(fila, linhas)
    return novos, pulados


def achar(linhas, id_):
    for r in linhas:
        if str(r["id"]) == str(id_):
            return r
    raise SystemExit(f"Não existe mensagem com ID {id_}.")


def enviadas_hoje(linhas, hoje=None):
    dia = hoje or date.today().isoformat()
    return sum(1 for r in linhas if r["status"] == "enviada" and (r.get("enviado_em") or "").startswith(dia))


def aprovar(linhas, id_, hoje=None):
    r = achar(linhas, id_)
    if r["status"] != "aguardando_aprovacao":
        raise SystemExit(f"Mensagem {id_} está como '{r['status']}', não pode ser aprovada agora.")
    r["status"] = "aprovada"
    r["aprovado_em"] = hoje or datetime.now().isoformat(timespec="minutes")


def rejeitar(linhas, id_):
    r = achar(linhas, id_)
    r["status"] = "rejeitada"


def link_envio(linhas, id_, bloqueados, cfg, hoje=None):
    r = achar(linhas, id_)
    if r["status"] != "aprovada":
        raise SystemExit(f"Só dá para gerar link de mensagem aprovada. Mensagem {id_} está '{r['status']}'.")
    if not r.get("link_site"):
        raise SystemExit("Mensagem sem link de site publicado. Não envie.")
    if r["telefone_normalizado"] in bloqueados:
        raise SystemExit("Este número está na lista de bloqueio. Não envie.")
    if enviadas_hoje(linhas, hoje) >= cfg["LIMITE_DIARIO"]:
        raise SystemExit(f"Limite diário de {cfg['LIMITE_DIARIO']} mensagens atingido. Continue amanhã.")
    return f"https://wa.me/{r['telefone_normalizado']}?text={urllib.parse.quote(r['mensagem'])}"


def marcar_enviada(linhas, id_, bloqueados, cfg, hoje=None):
    r = achar(linhas, id_)
    if r["status"] != "aprovada":
        raise SystemExit(f"Mensagem {id_} não está aprovada.")
    if enviadas_hoje(linhas, hoje) >= cfg["LIMITE_DIARIO"]:
        raise SystemExit(f"Limite diário de {cfg['LIMITE_DIARIO']} mensagens atingido.")
    r["status"] = "enviada"
    r["enviado_em"] = hoje or datetime.now().isoformat(timespec="minutes")


def bloquear(caminho_bloqueio, linhas, fila, telefone):
    # Mesma normalização do captador (ex.: "(51) 99999-0001" vira "5551999990001"), senão o bloqueio não encontra o contato.
    numero, _celular = captar_osm.normalizar_telefone(telefone)
    if not numero:
        raise SystemExit("Telefone inválido. Informe com DDD, ex.: (51) 99999-0001")
    config.adicionar_bloqueado(caminho_bloqueio, numero, date.today().isoformat(), "pediu para sair")
    for r in linhas:
        if r["telefone_normalizado"] == numero and r["status"] in ("aguardando_aprovacao", "aprovada"):
            r["status"] = "bloqueado"
    salvar(fila, linhas)


def revisar(fila, entrada=input, saida=print):
    """Mostra uma por uma as mensagens aguardando. Você escolhe: [a]provar, [r]ejeitar, [e]ditar, [p]ular, [s]air."""
    linhas = ler(fila)
    for r in linhas:
        if r["status"] != "aguardando_aprovacao":
            continue
        saida("-" * 60)
        saida(f"ID {r['id']} · {r['nome']} · {r['telefone_normalizado']}")
        saida(r["mensagem"])
        try:
            escolha = entrada("[a]provar  [r]ejeitar  [e]ditar  [p]ular  [s]air > ").strip().lower()
        except EOFError:  # entrada encerrou: salva o que já foi decidido e para
            break
        if escolha == "s":
            break
        if escolha == "a":
            r["status"], r["aprovado_em"] = "aprovada", datetime.now().isoformat(timespec="minutes")
        elif escolha == "r":
            r["status"] = "rejeitada"
        elif escolha == "e":
            novo = entrada("Novo texto (use \\n para quebra de linha): ")
            r["mensagem"] = novo.replace("\\n", "\n")
            if not r["mensagem"].strip():
                saida("Texto vazio. Mensagem continua aguardando.")
                continue
            r["status"], r["aprovado_em"] = "aprovada", datetime.now().isoformat(timespec="minutes")
        salvar(fila, linhas)
    salvar(fila, linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fila", default="dados/fila_whatsapp.csv")
    ap.add_argument("--finais", default="dados/leads_finais.csv")
    ap.add_argument("--bloqueados", default="dados/bloqueados.csv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gerar")
    sub.add_parser("listar")
    sub.add_parser("revisar")
    for nome in ("link", "marcar-enviada", "aprovar", "rejeitar"):
        p = sub.add_parser(nome)
        p.add_argument("id")
    p = sub.add_parser("bloquear")
    p.add_argument("telefone")
    a = ap.parse_args(argv)
    cfg = config.carregar()
    bloq = config.carregar_bloqueados(a.bloqueados)

    if a.cmd == "gerar":
        novos, pulados = gerar(a.finais, a.fila, bloq, cfg)
        print(f"{novos} mensagens criadas aguardando aprovação.")
        for nome, motivo in pulados:
            print(f"  não entrou: {nome} ({motivo})")
    elif a.cmd == "listar":
        for r in ler(a.fila):
            print(f"{r['id']:>4}  {r['status']:<22} {r['nome']} · {r['telefone_normalizado']}")
        print(f"Enviadas hoje: {enviadas_hoje(ler(a.fila))} de {cfg['LIMITE_DIARIO']}")
    elif a.cmd == "revisar":
        revisar(a.fila)
    elif a.cmd == "aprovar":
        linhas = ler(a.fila)
        aprovar(linhas, a.id)
        salvar(a.fila, linhas)
        print(f"Mensagem {a.id} aprovada.")
    elif a.cmd == "rejeitar":
        linhas = ler(a.fila)
        rejeitar(linhas, a.id)
        salvar(a.fila, linhas)
    elif a.cmd == "link":
        print(link_envio(ler(a.fila), a.id, bloq, cfg))
        print("Abra o link, confira a mensagem e envie você mesmo. Depois rode: marcar-enviada " + str(a.id))
    elif a.cmd == "marcar-enviada":
        linhas = ler(a.fila)
        marcar_enviada(linhas, a.id, bloq, cfg)
        salvar(a.fila, linhas)
        print(f"Mensagem {a.id} marcada como enviada.")
    elif a.cmd == "bloquear":
        bloquear(a.bloqueados, ler(a.fila), a.fila, a.telefone)
        print("Número adicionado à lista de bloqueio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
