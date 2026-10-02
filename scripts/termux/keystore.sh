#!/usr/bin/env bash
# Clé de signature de production de l'APK (une seule fois, sur le téléphone).
#   bash scripts/termux/keystore.sh
# Crée ~/footprono-release.jks, en fait une copie de sauvegarde dans Téléchargements,
# et prépare le texte (base64) à coller dans le secret GitHub FP_KEYSTORE_BASE64.
# La clé et ses mots de passe ne quittent jamais le téléphone et GitHub :
# ne les envoie à personne, pas même dans une discussion.
set -euo pipefail

KEY="$HOME/footprono-release.jks"
ALIAS="footprono"
DL="$HOME/storage/downloads"

if [ -e "$KEY" ]; then
    echo "La clé existe déjà : $KEY (jamais écrasée : la perdre empêche toute mise à jour de l'application)."
else
    command -v keytool >/dev/null 2>&1 || pkg install -y openjdk-17
    echo "Choisis un mot de passe solide (12 caractères ou plus) et NOTE-LE : il sera demandé deux fois."
    echo "Les questions (nom, organisation, ville…) : réponses libres, « FootProno » et « CI » suffisent."
    keytool -genkeypair -v -storetype PKCS12 -keystore "$KEY" -alias "$ALIAS" \
        -keyalg RSA -keysize 4096 -validity 10000
fi

[ -d "$DL" ] || termux-setup-storage
sleep 1
cp -n "$KEY" "$DL/footprono-release.jks" 2>/dev/null || true
base64 -w0 "$KEY" > "$DL/footprono-release-base64.txt"

echo
echo "Fichiers dans Téléchargements :"
echo "  footprono-release.jks          → SAUVEGARDE : copie-la aussi ailleurs (Google Drive, e-mail à toi-même)"
echo "  footprono-release-base64.txt   → texte à coller dans le secret GitHub FP_KEYSTORE_BASE64"
echo "                                   (c'est la clé elle-même : à SUPPRIMER une fois collé)"
if command -v termux-clipboard-set >/dev/null 2>&1; then
    termux-clipboard-set < "$DL/footprono-release-base64.txt"
    echo "Le texte base64 est aussi copié dans le presse-papiers."
fi
