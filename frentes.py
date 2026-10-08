"""Frentes de campanha: agrupamento geográfico dos municípios prioritários (notebook, seção 9)."""

NE = ["BA", "PE", "CE", "MA", "PI", "RN", "PB", "AL", "SE"]
RMSP = ["SAO PAULO", "SÃO PAULO", "GUARULHOS", "OSASCO", "SANTO ANDRÉ",
        "SÃO BERNARDO DO CAMPO", "SÃO CAETANO DO SUL", "DIADEMA", "MAUÁ", "BARUERI",
        "COTIA", "TABOÃO DA SERRA", "CARAPICUÍBA", "ITAPEVI", "EMBU DAS ARTES",
        "ITAQUAQUECETUBA", "SUZANO", "MOGI DAS CRUZES", "SANTOS", "SÃO VICENTE",
        "GUARUJÁ", "JANDIRA", "FERRAZ DE VASCONCELOS", "SANTANA DE PARNAÍBA"]


def frente(uf, municipio):
    if uf == "MG": return "Minas Gerais"
    if uf == "SP" and municipio in RMSP: return "Metropolitana de SP"
    if uf == "SP": return "Interior de SP"
    if uf in NE: return "Nordeste urbano"
    if uf in ("GO", "DF", "MT", "MS", "TO"): return "Goiás e entorno"
    if uf == "RJ": return "Rio de Janeiro"
    if uf in ("RS", "SC", "PR"): return "Sul"
    return "Norte e demais"
