"""Gera um site de demonstração estático (um arquivo HTML) por negócio.

Adaptado do gerador do projeto webbiz (oliverdadude/business-websites), com uso autorizado.
Mudança importante: não há textos de serviços, sobre a empresa, avaliações ou diferenciais.
Só aparecem dados reais do negócio (nome, categoria, bairro, telefone, endereço, horário).
As cores e fontes são só do estilo visual por ramo.
"""
import html
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from string import Template

import horarios

TEMPLATE = Template((Path(__file__).parent / "templates" / "site.html").read_text(encoding="utf-8"))

# Estilo visual por ramo: cores e fontes. Nenhum texto de marketing.
ESTILOS = {
    "alimentacao": {"fonts": ("Fraunces", "Inter", "family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Inter:wght@400;500;600"),
                    "cores": {"accent": "#b4471f", "on_accent": "#ffffff", "hero_bg": "#2a1a12", "hero_ink": "#fbf3ea",
                              "soft": "#fbf5ee", "ink": "#2a1a12", "muted": "#6b5a4e", "line": "#ecdccb"}},
    "beleza": {"fonts": ("Cormorant Garamond", "Jost", "family=Cormorant+Garamond:wght@500;600;700&family=Jost:wght@400;500;600"),
               "cores": {"accent": "#9d4b62", "on_accent": "#ffffff", "hero_bg": "#f6ebe8", "hero_ink": "#3b2229",
                         "soft": "#fbf6f4", "ink": "#3b2229", "muted": "#7a6168", "line": "#efdfdb"}},
    "obras_servicos": {"fonts": ("Archivo", "Inter", "family=Archivo:wght@600;800&family=Inter:wght@400;500;600"),
                       "cores": {"accent": "#f5b301", "accent_text": "#a16207", "on_accent": "#14213d", "hero_bg": "#14213d",
                                 "hero_ink": "#ffffff", "soft": "#f4f6fa", "ink": "#14213d", "muted": "#566079", "line": "#dfe4ee"}},
    "saude": {"fonts": ("Plus Jakarta Sans", "Plus Jakarta Sans", "family=Plus+Jakarta+Sans:wght@400;500;600;700;800"),
              "cores": {"accent": "#0f766e", "on_accent": "#ffffff", "hero_bg": "#0b2e2b", "hero_ink": "#ecfdf5",
                        "soft": "#f0fdfa", "ink": "#0b2e2b", "muted": "#4b6b66", "line": "#d5ebe7"}},
    "automotivo": {"fonts": ("Oswald", "Inter", "family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600"),
                   "cores": {"accent": "#dc2626", "on_accent": "#ffffff", "hero_bg": "#111111", "hero_ink": "#ffffff",
                             "soft": "#f5f5f5", "ink": "#111111", "muted": "#555555", "line": "#e5e5e5"}},
    "academia": {"fonts": ("Oswald", "Inter", "family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600"),
                 "cores": {"accent": "#16a34a", "on_accent": "#052e16", "hero_bg": "#052e16", "hero_ink": "#f0fdf4",
                           "soft": "#f0fdf4", "ink": "#052e16", "muted": "#4d6b57", "line": "#d1f0dc"}},
    "geral": {"fonts": ("Plus Jakarta Sans", "Plus Jakarta Sans", "family=Plus+Jakarta+Sans:wght@400;500;600;700;800"),
              "cores": {"accent": "#2563eb", "on_accent": "#ffffff", "hero_bg": "#0f172a", "hero_ink": "#f8fafc",
                        "soft": "#f8fafc", "ink": "#0f172a", "muted": "#475569", "line": "#e2e8f0"}},
}

# Palavras-chave do OpenStreetMap (em inglês, como o OSM grava) que indicam o ramo.
RAMOS = [
    ("alimentacao", ("restaurant", "cafe", "bakery", "pizza", "fast_food", "bar", "pub", "ice_cream", "deli", "butcher",
                     "food", "coffee", "greengrocer", "confectionery", "beverages", "takeaway")),
    ("beleza", ("hairdresser", "beauty", "nails", "barber", "hair", "cosmetics", "tattoo", "spa", "massage", "salon")),
    ("obras_servicos", ("plumber", "electrician", "carpenter", "painter", "builder", "roofer", "hardware", "locksmith",
                        "craft", "joiner", "tiler", "gardener", "cleaning")),
    ("saude", ("dentist", "doctor", "clinic", "pharmacy", "physiotherapist", "optician", "veterinary", "chemist",
               "medical", "healthcare", "psychotherapist", "chiropractor")),
    ("automotivo", ("car_repair", "car", "tyres", "car_wash", "auto_parts", "motorcycle")),
    ("academia", ("fitness_centre", "gym", "sports_centre", "yoga", "dance", "pilates", "personal_trainer")),
]

ICONES = {
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "map-pin": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
    "chat": '<path d="M21 11.5a8.5 8.5 0 0 1-12.6 7.4L3 21l2-5.2A8.5 8.5 0 1 1 21 11.5z"/>',
}


def icone(nome, tamanho=20):
    return (f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONES[nome]}</svg>')


def ramo_de(categoria):
    texto = (categoria or "").lower()
    palavras = set(re.split(r"[=;,/\s]+", texto))
    for nome, chaves in RAMOS:
        if any(c in palavras or c in texto for c in chaves):
            return nome
    return "geral"


# Rótulos em português para os valores de categoria mais comuns do OpenStreetMap.
ROTULOS_CATEGORIA = {
    "bakery": "Padaria", "cafe": "Cafeteria", "restaurant": "Restaurante", "pizza": "Pizzaria",
    "fast_food": "Lanchonete", "bar": "Bar", "pub": "Pub", "ice_cream": "Sorveteria", "butcher": "Açougue",
    "deli": "Delicatessen", "greengrocer": "Hortifrúti", "confectionery": "Confeitaria", "beverages": "Bebidas",
    "coffee": "Cafeteria", "supermarket": "Supermercado", "convenience": "Conveniência", "clothes": "Roupas",
    "shoes": "Calçados", "jewelry": "Joalheria", "hairdresser": "Cabeleireiro", "beauty": "Salão de beleza",
    "barber": "Barbearia", "nails": "Manicure", "cosmetics": "Cosméticos", "tattoo": "Tatuagem",
    "massage": "Massagem", "electronics": "Eletrônicos", "furniture": "Móveis", "hardware": "Ferragens",
    "florist": "Floricultura", "bicycle": "Bicicletaria", "car_repair": "Oficina mecânica",
    "car_wash": "Lava-rápido", "car_parts": "Autopeças", "tyres": "Borracharia", "car": "Concessionária",
    "electrician": "Eletricista", "plumber": "Encanador", "carpenter": "Marceneiro", "painter": "Pintor",
    "locksmith": "Chaveiro", "roofer": "Telhadista", "builder": "Construtora", "gardener": "Jardineiro",
    "dentist": "Dentista", "doctor": "Consultório médico", "clinic": "Clínica", "pharmacy": "Farmácia",
    "physiotherapist": "Fisioterapia", "optician": "Ótica", "veterinary": "Veterinário",
    "psychotherapist": "Psicologia", "chiropractor": "Quiropraxia", "gym": "Academia",
    "fitness_centre": "Academia", "yoga": "Yoga", "dance": "Dança", "pilates": "Pilates",
    "hotel": "Hotel", "guest_house": "Pousada", "hostel": "Hostel", "lawyer": "Advocacia",
    "accountant": "Contabilidade", "estate_agent": "Imobiliária", "insurance": "Seguros",
    "architect": "Arquitetura", "photographer": "Fotografia", "printing": "Gráfica",
    "travel_agent": "Agência de viagens", "notary": "Cartório", "office": "Escritório",
}


def categoria_bonita(categoria):
    valor = (categoria or "").split("=", 1)[-1].split(";")[0].strip()
    if not valor:
        return ""
    if valor in ROTULOS_CATEGORIA:
        return ROTULOS_CATEGORIA[valor]
    # Valor fora do dicionário: sem texto em inglês, mostra um rótulo genérico em vez de inventar tradução.
    return "Negócio local"


def slugify(texto):
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:60] or "negocio"


def link_whatsapp(telefone_normalizado):
    return f"https://wa.me/{telefone_normalizado}" if telefone_normalizado else ""


def _li(icone_nome, rotulo, valor_html):
    return (f'<li><small>{rotulo}</small><span class="row" style="display:flex;gap:10px;align-items:center">'
            f'{icone(icone_nome)}{valor_html}</span></li>')


def renderizar(lead, cfg, final=False):
    """Devolve o HTML do site. final=True tira o aviso de demonstração e a marca noindex."""
    e = lambda s: html.escape(str(s or ""), quote=True)
    nome = (lead.get("nome") or "").strip()
    bairro = (lead.get("bairro") or "").strip()
    cidade = (lead.get("cidade") or "").strip()
    categoria = categoria_bonita(lead.get("categoria"))
    endereco = (lead.get("endereco") or "").strip()
    telefone = (lead.get("telefone") or "").strip()
    wa_num = (lead.get("telefone_normalizado") or "").strip()
    estilo = ESTILOS[ramo_de(lead.get("categoria"))]
    cores = {"accent_text": estilo["cores"]["accent"], **estilo["cores"]}
    display_font, body_font, font_query = estilo["fonts"]
    local = " · ".join(x for x in [bairro, cidade] if x)
    estudio = e(cfg.get("estudio") or "Estúdio de demonstração")

    contato = []
    if telefone:
        contato.append(_li("phone", "Telefone", f'<a href="tel:+{e(wa_num)}">{e(telefone)}</a>' if wa_num else e(telefone)))
    if endereco:
        contato.append(_li("map-pin", "Endereço", f'<a href="#visit">{e(endereco)}</a>'))

    botao_wa = ""
    if wa_num:
        botao_wa = (f'<a class="btn btn-primary" href="{e(link_whatsapp(wa_num))}" target="_blank" rel="noopener">'
                    f'{icone("chat", 18)} Falar no WhatsApp</a>')
    botao_tel = (f'<a class="btn btn-outline" href="tel:+{e(wa_num)}">{icone("phone", 18)} Ligar</a>'
                 if wa_num else "")

    horario = horarios.parse(lead.get("opening_hours"))
    status = ""
    if horario:
        linhas = "".join(
            f'<tr data-day="{i}"><td>{dia}</td><td>{e(texto)}</td></tr>'
            for i, (dia, texto) in enumerate(horario["texto"]))
        horas_html = f"<table>{linhas}</table>"
        horas_json = json.dumps(horario["faixas"])
        status = ('<div class="status" id="open-status"><span class="dot"></span><span>&nbsp;</span></div>')
    elif lead.get("opening_hours"):
        horas_html = f'<p class="raw">{e(lead["opening_hours"]).replace(";", "<br>")}</p>'
        horas_json = "null"
    else:
        horas_html = ('<p class="raw">Horário não informado. Entre em contato pelo telefone para confirmar.</p>')
        horas_json = "null"

    # O link para abrir o mapa fica sempre visível, para o visitante chegar ao local mesmo se o mapa embutido falhar.
    consulta = urllib.parse.quote_plus(" ".join(x for x in [nome, endereco, cidade] if x))
    link_mapa = (f'<a class="btn btn-outline" style="margin-top:14px" href="https://www.openstreetmap.org/search?query={consulta}" '
                 f'target="_blank" rel="noopener">Abrir no mapa →</a>')
    lat, lon = lead.get("lat"), lead.get("lon")
    mapa = ""
    try:
        la, lo = float(lat), float(lon)
        caixa = f"{lo - .006},{la - .0035},{lo + .006},{la + .0035}"
        mapa = (f'<iframe title="Mapa: {e(nome)}" loading="lazy" '
                f'src="https://www.openstreetmap.org/export/embed.html?bbox={caixa}&amp;layer=mapnik&amp;marker={la},{lo}"></iframe>')
    except (TypeError, ValueError):
        mapa = (f'<div class="nomap"><p style="margin:0;color:var(--ink);font-weight:600">{e(endereco or local or nome)}</p></div>')

    schema = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": nome}
    if telefone:
        schema["telephone"] = telefone
    if endereco:
        schema["address"] = {"@type": "PostalAddress", "streetAddress": endereco, "addressLocality": cidade}

    favicon = urllib.parse.quote(
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='16' "
        f"fill='{cores['accent']}'/><text x='32' y='44' font-size='34' font-family='Arial' font-weight='700' "
        f"text-anchor='middle' fill='{cores['on_accent']}'>{e(nome[:1].upper())}</text></svg>")

    aviso = "" if final else (
        f'<div class="preview-bar">Site de demonstração gratuito feito para {e(nome)} por {estudio}. '
        f'Não é o site oficial do negócio.</div>')

    return TEMPLATE.substitute(
        title=e(f"{nome} | {categoria}" if categoria else nome),
        description=e(f"{nome}{' em ' + local if local else ''}. Informações de contato e horário."),
        favicon=favicon,
        font_query=font_query,
        display_font=display_font,
        body_font=body_font,
        schema=json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"),
        preview_bar=aviso,
        robots_meta="" if final else '\n<meta name="robots" content="noindex">',
        name=e(nome),
        eyebrow=e(" · ".join(x for x in [categoria, bairro] if x) or "Negócio local"),
        tagline=e(f"{categoria} em {local}" if categoria and local else (categoria or local or "Negócio local")),
        whatsapp_button=botao_wa,
        call_button=botao_tel,
        contact_items="".join(contato),
        status_line=status,
        address_line=e(endereco or local or "Endereço não informado"),
        hours=horas_html,
        hours_json=horas_json,
        map=mapa,
        map_link=link_mapa,
        footer_location=e(f" · {local}" if local else ""),
        credit=f"Demonstração por {estudio}",
        **cores,
    )


def gerar_arquivo(lead, cfg, pasta_sites, final=False):
    """Grava sites/<slug>/index.html e devolve o slug."""
    slug = lead.get("slug") or f"{slugify(lead.get('nome'))}-{lead.get('osm_id') or 'x'}"
    pasta = Path(pasta_sites) / slug
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "index.html").write_text(renderizar(lead, cfg, final=final), encoding="utf-8")
    return slug
