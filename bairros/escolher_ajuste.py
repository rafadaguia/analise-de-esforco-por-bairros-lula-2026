#!/usr/bin/env python3
"""Lista as UFs instáveis (critério do selo) ou incorpora o reajuste longo onde ele for melhor.

  python bairros/escolher_ajuste.py U4 instaveis      # imprime as UFs com R-hat > 1,05 ou 3+ cadeias descartadas
  python bairros/escolher_ajuste.py U4 incorporar [MC_extralongo]   # copia a pasta (padrão MC_longo) -> MC por UF, se for melhor
Melhor = menos instável: primeiro sai do critério do selo (R-hat <= 1,05 e 4+ cadeias boas), depois menor R-hat.
"""
import glob, json, math, os, shutil, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def instavel(boas, rh):
    return rh > 1.05 or boas <= 3


def diag(pasta):
    out = {}
    for f in glob.glob(os.path.join(pasta, "diag_??.json")):
        d = json.load(open(f))
        rh = d.get("rhat_max")
        rh = 9.0 if rh is None or (isinstance(rh, float) and math.isnan(rh)) else rh
        out[d["uf"]] = (len(d.get("logp_cadeias", [0] * 6)) - len(d.get("descartadas", [])), rh)
    return out


if __name__ == "__main__":
    u, acao = sys.argv[1], sys.argv[2]
    fonte = sys.argv[3] if len(sys.argv) > 3 else "MC_longo"
    mc, lg = os.path.join(RAIZ, "variantes", u, "MC"), os.path.join(RAIZ, "variantes", u, fonte)
    d = diag(mc)
    if acao == "instaveis":
        print(" ".join(sorted(k for k, (boas, rh) in d.items() if instavel(boas, rh))))
    else:
        l = diag(lg)
        guarda = os.path.join(RAIZ, "variantes", u, "MC_antes_" + fonte.replace("MC_", ""))
        os.makedirs(guarda, exist_ok=True)
        for uf, (boas, rh) in l.items():
            b0, r0 = d.get(uf, (0, 9.0))
            melhor = (instavel(b0, r0) and not instavel(boas, rh)) or (instavel(b0, r0) == instavel(boas, rh) and rh < r0)
            print(f"{uf}: original {b0} cadeias, R-hat {r0:.3f} | longo {boas}, {rh:.3f} -> {'longo' if melhor else 'original'}")
            if melhor:
                for f in (f"post_{uf}.nc", f"dados_{uf}.npz", f"diag_{uf}.json"):
                    shutil.copy(os.path.join(mc, f), os.path.join(guarda, f))
                    shutil.copy(os.path.join(lg, f), os.path.join(mc, f))
