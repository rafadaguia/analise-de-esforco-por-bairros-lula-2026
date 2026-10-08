#!/usr/bin/env python3
"""Lista as UFs instáveis (critério do selo) ou incorpora o reajuste longo onde ele for melhor.

  python bairros/escolher_ajuste.py U4 instaveis      # imprime as UFs com R-hat > 1,05 ou 3+ cadeias descartadas
  python bairros/escolher_ajuste.py U4 incorporar     # copia MC_longo -> MC por UF, se tiver mais cadeias boas (ou, empatando, menor R-hat)
"""
import glob, json, math, os, shutil, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def diag(pasta):
    out = {}
    for f in glob.glob(os.path.join(pasta, "diag_??.json")):
        d = json.load(open(f))
        rh = d.get("rhat_max")
        rh = 9.0 if rh is None or (isinstance(rh, float) and math.isnan(rh)) else rh
        out[d["uf"]] = (6 - len(d.get("descartadas", [])), rh)
    return out


if __name__ == "__main__":
    u, acao = sys.argv[1], sys.argv[2]
    mc, lg = os.path.join(RAIZ, "variantes", u, "MC"), os.path.join(RAIZ, "variantes", u, "MC_longo")
    d = diag(mc)
    if acao == "instaveis":
        print(" ".join(sorted(k for k, (boas, rh) in d.items() if rh > 1.05 or boas <= 3)))
    else:
        l = diag(lg)
        os.makedirs(os.path.join(RAIZ, "variantes", u, "MC_2000"), exist_ok=True)
        for uf, (boas, rh) in l.items():
            b0, r0 = d.get(uf, (0, 9.0))
            melhor = boas > b0 or (boas == b0 and rh < r0)
            print(f"{uf}: original {b0} cadeias, R-hat {r0:.3f} | longo {boas}, {rh:.3f} -> {'longo' if melhor else 'original'}")
            if melhor:
                for f in (f"post_{uf}.nc", f"dados_{uf}.npz", f"diag_{uf}.json"):
                    shutil.copy(os.path.join(mc, f), os.path.join(RAIZ, "variantes", u, "MC_2000", f))
                    shutil.copy(os.path.join(lg, f), os.path.join(mc, f))
