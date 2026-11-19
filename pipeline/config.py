"""Configuração e lista de bloqueio, compartilhadas pelos scripts.

Lê o arquivo pipeline/.env (formato CHAVE=valor). Nenhuma chave de API é necessária para o teste com OSM.
"""
import csv
import os
import re
from pathlib import Path

PASTA = Path(__file__).resolve().parent
PADROES = {
    "ESTUDIO": "",                 # nome do seu negócio, como aparece nas mensagens e nos sites
    "SITE_BASE_URL": "",           # endereço público onde os sites serão publicados, ex.: https://seu-site.netlify.app
    "LIMITE_DIARIO": "25",         # mensagens por dia (aceito de 20 a 30)
}
COLUNAS_BLOQUEIO = ["telefone_normalizado", "data", "motivo"]


def carregar(caminho_env=None):
    cfg = dict(PADROES)
    arq = Path(caminho_env) if caminho_env else PASTA / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            cfg[chave.strip()] = valor.strip().strip('"').strip("'")
    for chave in cfg:  # variáveis do ambiente têm prioridade
        if chave in os.environ:
            cfg[chave] = os.environ[chave]
    limite = int(cfg["LIMITE_DIARIO"])
    if not 20 <= limite <= 30:
        raise SystemExit("LIMITE_DIARIO precisa estar entre 20 e 30.")
    cfg["LIMITE_DIARIO"] = limite
    return cfg


def _so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def carregar_bloqueados(caminho):
    p = Path(caminho)
    if not p.exists():
        return set()
    with open(p, newline="", encoding="utf-8") as f:
        return {_so_digitos(r.get("telefone_normalizado")) for r in csv.DictReader(f) if r.get("telefone_normalizado")}


def adicionar_bloqueado(caminho, telefone, data, motivo):
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    novo = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_BLOQUEIO)
        if novo:
            w.writeheader()
        w.writerow({"telefone_normalizado": _so_digitos(telefone), "data": data, "motivo": motivo})
