"""Passo 3a: captura empresas do OpenStreetMap com telefone e SEM site marcado.

Uso (área ao redor de um ponto, bom para teste):
  python3 captar_osm.py --centro -30.0277 -51.2065 --raio 1500 --saida dados/leads_osm.csv

Fonte: Overpass API (OpenStreetMap), gratuita, sem chave. Usa identificação genérica no cabeçalho.
Ressalva: "sem site" aqui quer dizer "sem a tag website no OSM". Isso NÃO prova que a empresa não tem site.
Por isso a coluna verificar_site vem sempre "sim": é preciso conferir antes de enviar qualquer mensagem.
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
]
USER_AGENT = "pipeline-leads-teste/0.1 (captura para teste local)"
CHAVES = ["amenity", "shop", "craft", "office", "healthcare", "tourism", "leisure"]
EXCLUIR_AMENITY = {"bench", "parking", "toilets", "waste_basket", "post_box", "atm", "recycling", "shelter",
                   "drinking_water", "fire_station", "police", "hospital", "school", "kindergarten", "university",
                   "place_of_worship", "library", "post_office", "fuel", "charging_station", "bicycle_parking"}
COLUNAS = ["osm_id", "nome", "categoria", "telefone", "telefone_normalizado", "whatsapp_provavel",
           "endereco", "bairro", "cidade", "lat", "lon", "opening_hours", "verificar_site"]


def montar_consulta(lat, lon, raio):
    partes = "".join(f'nwr(around:{raio},{lat},{lon})["name"]["{c}"];' for c in CHAVES)
    return f"[out:json][timeout:90];({partes});out center tags;"


def normalizar_telefone(bruto):
    """Devolve (numero_com_55, e_celular). Vazio se não parecer telefone brasileiro."""
    primeiro = re.split(r"[;/]", bruto or "")[0]
    d = re.sub(r"\D", "", primeiro)
    if d.startswith("0055"):
        d = d[4:]
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11):
        return "", False
    celular = len(d) == 11 and d[2] == "9"
    return "55" + d, celular


def categoria_de(tags):
    for c in CHAVES:
        if c in tags:
            return f"{c}={tags[c]}"
    return ""


def elemento_para_lead(el):
    tags = el.get("tags", {})
    nome = (tags.get("name") or "").strip()
    if not nome or tags.get("amenity") in EXCLUIR_AMENITY:
        return None
    if any(tags.get(k) for k in ("website", "contact:website", "url", "contact:url")):
        return None  # já tem site marcado: fica de fora
    bruto = tags.get("phone") or tags.get("contact:phone") or ""
    numero, celular = normalizar_telefone(bruto)
    if not numero:
        return None  # sem telefone válido, não há como contatar
    centro = el.get("center") or {}
    lat = el.get("lat", centro.get("lat", ""))
    lon = el.get("lon", centro.get("lon", ""))
    endereco = " ".join(x for x in [tags.get("addr:street", ""), tags.get("addr:housenumber", "")] if x)
    return {
        "osm_id": f"{el.get('type', 'n')}{el.get('id')}",
        "nome": nome,
        "categoria": categoria_de(tags),
        "telefone": bruto.split(";")[0].strip(),
        "telefone_normalizado": numero,
        "whatsapp_provavel": "sim" if celular else "nao",
        "endereco": endereco,
        "bairro": tags.get("addr:suburb") or tags.get("addr:neighbourhood") or "",
        "cidade": tags.get("addr:city", ""),
        "lat": lat,
        "lon": lon,
        "opening_hours": tags.get("opening_hours", ""),
        "verificar_site": "sim",
    }


def buscar(consulta, tentativas=3):
    dados = urllib.parse.urlencode({"data": consulta}).encode("utf-8")
    ultimo = None
    for tentativa in range(tentativas):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=dados, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as erro:
                ultimo = erro
        time.sleep(5 * (tentativa + 1))
    raise SystemExit(f"Não consegui consultar o OpenStreetMap após {tentativas} tentativas: {ultimo}")


def capturar(lat, lon, raio):
    dados = buscar(montar_consulta(lat, lon, raio))
    leads, vistos = [], set()
    for el in dados.get("elements", []):
        lead = elemento_para_lead(el)
        if lead and lead["osm_id"] not in vistos:
            vistos.add(lead["osm_id"])
            leads.append(lead)
    return leads


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--centro", nargs=2, type=float, metavar=("LAT", "LON"), required=True)
    ap.add_argument("--raio", type=int, default=1500, help="raio em metros (padrão 1500)")
    ap.add_argument("--saida", default="dados/leads_osm.csv")
    a = ap.parse_args(argv)
    if a.raio > 5000:
        sys.exit("Para teste, use raio até 5000 m. Raios maiores pesam no servidor do OSM.")
    leads = capturar(a.centro[0], a.centro[1], a.raio)
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    with open(a.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        for lead in leads:
            w.writerow({c: lead.get(c, "") for c in COLUNAS})
    print(f"{len(leads)} negócios com telefone e sem site marcado gravados em {a.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
