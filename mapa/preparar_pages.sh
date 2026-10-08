#!/bin/bash
# Monta a pasta do mapa por bairro pronta para o GitHub Pages de um repositório próprio (não deste).
# Uso: mapa/preparar_pages.sh [destino]   (padrão: docs/, pasta do GitHub Pages)
# Pré-requisito: mapa/construir_mapa_bairros.py já rodado.
set -e
cd "$(dirname "$0")/.."
D="${1:-docs}"
# trava: só substitui uma pasta vazia ou que já seja este mapa (no repositório da v2.0, docs/ é outro site)
if [ -d "$D" ] && [ -n "$(ls -A "$D")" ] && [ ! -f "$D/unidades.pmtiles" ]; then
  echo "ERRO: $D existe e não é o mapa por bairro; nada foi apagado"; exit 1
fi
rm -rf "$D"; mkdir -p "$D"
cp -R mapa/bairros/. "$D/"
touch "$D/.nojekyll"     # o Jekyll do Pages não deve processar a pasta
# o GitHub recusa arquivos acima de 100 MB; o Pages não serve arquivos do Git LFS
find "$D" -type f -size +95M -print | grep . && { echo "ERRO: arquivo acima de 95 MB"; exit 1; } || true
echo "pronto: $D ($(du -sh "$D" | cut -f1))"
