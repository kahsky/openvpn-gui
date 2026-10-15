"""
Minimal i18n — English by default, French when the user's locale is French.

Usage:  from .i18n import _ ;  _("Connect")
Strings not present in the table are returned unchanged.
"""
import os

_FR = {}  # filled below


def _detect_lang() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val.split(":")[0].split(".")[0].split("_")[0].lower()
    return "en"


LANG = _detect_lang()


def _(text: str) -> str:
    if LANG == "fr":
        return _FR.get(text, text)
    return text


# ── French strings ─────────────────────────────────────────────────────────── #
_FR.update({
    # Dialogs
    "New manual profile": "Nouveau profil manuel",
    "_Cancel": "_Annuler",
    "C_reate": "C_réer",
    "PROFILE NAME": "NOM DU PROFIL",
    "e.g. Office VPN": "ex. VPN Bureau",
    "HOST": "HÔTE",
    "PORT": "PORT",
    "PROTOCOL": "PROTOCOLE",
    "OpenVPN default: 1194": "Valeur par défaut OpenVPN : 1194",
    "CA CERTIFICATE": "CERTIFICAT CA",
    "Select CA certificate": "Choisir le certificat CA",
    "Certificates (*.crt, *.pem, *.cer)": "Certificats (*.crt, *.pem, *.cer)",
    "All files": "Tous les fichiers",
    "USERNAME": "UTILISATEUR",
    "Enter username…": "Nom d'utilisateur…",
    "PASSWORD": "MOT DE PASSE",
    "Enter password…": "Mot de passe…",
    "Remember credentials (stored in system keyring)": "Mémoriser les identifiants (trousseau système)",
    "A profile with this name already exists.": "Un profil portant ce nom existe déjà.",
    "Define the server yourself — no .ovpn file needed.\n"
    "Credentials are asked at connection time or saved in the system keyring.":
        "Définissez le serveur vous-même — aucun fichier .ovpn requis.\n"
        "Les identifiants sont demandés à la connexion ou mémorisés dans le trousseau système.",
    "Optional here, but nearly every server requires it (OpenVPN refuses to start without a CA).":
        "Facultatif ici, mais presque tous les serveurs l'exigent (OpenVPN refuse de démarrer sans CA).",
    "A modern OpenVPN client for Linux Mint / Ubuntu.\nApplication created by Dukiwi.":
        "Un client OpenVPN moderne pour Linux Mint / Ubuntu.\nApplication créée par Dukiwi.",
    # Tray
    "Connect": "Connecter",
    "Disconnect": "Déconnecter",
    "Disconnected": "Déconnecté",
    "Open": "Ouvrir",
    "Quit": "Quitter",
    "Connected to {name}": "Connecté à {name}",
    "Connecting to {name}…": "Connexion à {name}…",
    "Cancel": "Annuler",
    # Log view
    "VERBOSE CONNECTION LOG": "JOURNAL DÉTAILLÉ DE CONNEXION",
    "Copy log to clipboard": "Copier le journal",
    "Clear log": "Effacer le journal",
    # Header / sidebar
    "by Dukiwi": "par Dukiwi",
    "Import .ovpn config file": "Importer un fichier .ovpn",
    "New manual profile (host, port, user, password)": "Nouveau profil manuel (hôte, port, utilisateur, mot de passe)",
    "About OpenVPN GUI": "À propos d'OpenVPN GUI",
    "VPN PROFILES": "PROFILS VPN",
    "No profiles yet.\nImport a .ovpn file\nor create one manually.": "Aucun profil.\nImportez un fichier .ovpn\nou créez-en un manuellement.",
    "+ Import .ovpn": "+ Importer un .ovpn",
    "✎ Manual profile": "✎ Profil manuel",
    "Select a profile, import a .ovpn file\nor define a server manually.": "Sélectionnez un profil, importez un .ovpn\nou définissez un serveur manuellement.",
    "Import .ovpn": "Importer un .ovpn",
    "Create manually": "Créer manuellement",
    "Remove this profile": "Supprimer ce profil",
    # Form
    "CONNECT": "CONNECTER",
    "Details": "Détails",
    "SERVER": "SERVEUR",
    "Saved to the NetworkManager profile when you leave a field or connect.": "Enregistré dans le profil NetworkManager en quittant un champ ou à la connexion.",
    "This profile lists {n} servers; editing here keeps only the first one.": "Ce profil liste {n} serveurs ; la modification ici ne conserve que le premier.",
    "CREDENTIALS": "IDENTIFIANTS",
    "Show / hide password": "Afficher / masquer le mot de passe",
    "No server defined": "Aucun serveur défini",
    "Saving server settings: {host}:{port} ({proto})": "Enregistrement du serveur : {host}:{port} ({proto})",
    "Could not save server settings: {msg}": "Impossible d'enregistrer le serveur : {msg}",
    "Please enter the server host before connecting.": "Veuillez saisir l'hôte du serveur avant de vous connecter.",
    "Credentials stored in the system keyring.": "Identifiants enregistrés dans le trousseau système.",
    "Keyring error: {msg}": "Erreur du trousseau : {msg}",
    "Same credentials as the last successful connection — NetworkManager's cached secrets are kept.": "Mêmes identifiants que la dernière connexion réussie — les secrets en cache de NetworkManager sont conservés.",
    # Connecting
    "Preparing": "Préparation",
    "Authenticating": "Authentification",
    "Establishing tunnel": "Établissement du tunnel",
    "Configuring network": "Configuration réseau",
    "See more": "Voir plus",
    "See less": "Voir moins",
    "Connecting to {server}…": "Connexion à {server}…",
    "Asking NetworkManager to bring the tunnel up…": "Demande à NetworkManager de monter le tunnel…",
    "Connecting…": "Connexion…",
    "CANCEL": "ANNULER",
    "CANCELLING…": "ANNULATION…",
    "CONNECTED": "CONNECTÉ",
    "FAILED": "ÉCHEC",
    "Authentication failed (AUTH_FAILED) — check the username and password.": "Échec de l'authentification (AUTH_FAILED) — vérifiez l'utilisateur et le mot de passe.",
    "Tunnel established.": "Tunnel établi.",
    "Connected to {name}.": "Connecté à {name}.",
    "Connection cancelled by user.": "Connexion annulée par l'utilisateur.",
    "Connection failed: {msg}": "Échec de la connexion : {msg}",
    "Cancel requested — bringing the connection down.": "Annulation demandée — arrêt de la connexion.",
    "NetworkManager VPN state: {s}": "État VPN NetworkManager : {s}",
    # Connected / traffic
    "DOWNLOAD": "RÉCEPTION",
    "UPLOAD": "ÉMISSION",
    "IP {ip}": "IP {ip}",
    "via {server}": "via {server}",
    "Received {v}": "Reçu {v}",
    "Sent {v}": "Envoyé {v}",
    "Connected": "Connecté",
    "DISCONNECT": "DÉCONNECTER",
    "Tunnel up on {iface} — IP {ip}, gateway {gw}": "Tunnel actif sur {iface} — IP {ip}, passerelle {gw}",
    "Could not determine the tunnel interface — traffic view unavailable.": "Interface du tunnel introuvable — vue du trafic indisponible.",
    "Peak ↓ {dl}  ↑ {ul}": "Pic ↓ {dl}  ↑ {ul}",
    "Connected {d}": "Connecté {d}",
    "DISCONNECTING…": "DÉCONNEXION…",
    "Disconnecting…": "Déconnexion…",
    "Disconnecting {name}": "Déconnexion de {name}",
    "Disconnected.": "Déconnecté.",
    "Disconnect failed: {msg}": "Échec de la déconnexion : {msg}",
    "Connection became active (external activation detected).": "Connexion devenue active (activation externe détectée).",
    "Connection dropped — tunnel is no longer active.": "Connexion perdue — le tunnel n'est plus actif.",
    "The VPN connection was lost.": "La connexion VPN a été perdue.",
    # Import / delete
    "Import OpenVPN Config": "Importer une configuration OpenVPN",
    "_Import": "_Importer",
    "OpenVPN Config (*.ovpn, *.conf)": "Configuration OpenVPN (*.ovpn, *.conf)",
    "Profile imported": "Profil importé",
    "\"{name}\" has been added.": "« {name} » a été ajouté.",
    "Import failed": "Échec de l'importation",
    "Manual profile \"{name}\" created ({host}:{port} {proto}).": "Profil manuel « {name} » créé ({host}:{port} {proto}).",
    "Delete \"{name}\"?": "Supprimer « {name} » ?",
    "This will remove the profile from NetworkManager.\nSaved credentials will also be deleted.": "Le profil sera retiré de NetworkManager.\nLes identifiants mémorisés seront aussi supprimés.",
    "_Delete": "_Supprimer",
    "Delete failed": "Échec de la suppression",
})
