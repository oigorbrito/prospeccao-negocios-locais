"""Converte o texto de horário do OpenStreetMap (ex.: "Mo-Fr 09:00-18:00; Sa 09:00-12:00; Su off") em uma tabela semanal.

Entende as formas simples. Qualquer coisa mais complexa (feriados, meses, semanas alternadas) devolve None,
e o site mostra o texto original.
"""
import re

DIAS_OSM = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORA = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _dias(spec):
    saida = []
    for parte in spec.split(","):
        if "-" in parte:
            a, b = parte.split("-", 1)
            if a not in DIAS_OSM or b not in DIAS_OSM:
                return None
            i, j = DIAS_OSM.index(a), DIAS_OSM.index(b)
            saida += [DIAS_OSM[k % 7] for k in range(i, j + 1 if j >= i else j + 8)]
        elif parte in DIAS_OSM:
            saida.append(parte)
        else:
            return None
    return saida


def _faixas(spec):
    """Lista de (inicio, fim) em minutos. Lista vazia = fechado. None = não entendi."""
    spec = spec.strip()
    if spec.lower() in ("off", "closed"):
        return []
    faixas = []
    for r in (x.strip() for x in spec.split(",")):
        m = HORA.match(r)
        if not m:
            return None
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 24 or h2 > 24 or m1 > 59 or m2 > 59:
            return None
        faixas.append((h1 * 60 + m1, h2 * 60 + m2))
    return faixas


def _texto(faixas):
    if not faixas:
        return "Fechado"
    return ", ".join(f"{a // 60:02d}:{a % 60:02d}–{b // 60:02d}:{b % 60:02d}" for a, b in faixas)


def parse(texto):
    """Devolve {'texto': [(dia_pt, texto_horario)x7], 'faixas': [[(ini,fim)...]x7]} ou None."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if texto == "24/7":
        faixas = [[(0, 1440)] for _ in range(7)]
    else:
        semana = {}
        for regra in filter(None, (r.strip() for r in texto.split(";"))):
            if regra.startswith(("PH", "SH")):
                continue
            m = re.match(r"^([A-Za-z,\-]+)\s+(.+)$", regra)
            if m and m.group(1)[:2] in DIAS_OSM:
                dias, faixas_regra = _dias(m.group(1)), _faixas(m.group(2))
            else:
                dias, faixas_regra = DIAS_OSM, _faixas(regra)
            if dias is None or faixas_regra is None:
                return None
            for d in dias:
                semana[d] = faixas_regra
        if not semana:
            return None
        faixas = [semana.get(d, []) for d in DIAS_OSM]
    return {
        "texto": [(DIAS_PT[i], _texto(f)) for i, f in enumerate(faixas)],
        "faixas": [[list(x) for x in f] for f in faixas],
    }
