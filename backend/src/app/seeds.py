"""Seed the database with demo data.

Only the 5 real 42 team accounts exist as users - no throwaway "demo user"
and no crowd of fake students. Listings, conversations, sales, reviews,
friends, a block and reports are all between these same 5 people, so
everything a moderator or a seller can see traces back to someone who
actually uses this app. Ratings are never set directly: they only move the
way the real API moves them, by summing real Review rows as they're
created, so GET /users/{id}'s average is always backed by something that
really happened.

Idempotent: skipped entirely if any listing already exists.
"""

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import async_session
from app.models import (
    Category,
    Conversation,
    Friend,
    Listing,
    ListingFavorite,
    ListingImage,
    Location,
    Message,
    Report,
    Review,
    User,
    UserBlock,
)
from app.models.enums import FriendStatus, ListingStatus, ReportStatus

MOCK_NOW = datetime(2026, 9, 9, 17, 0, 0, tzinfo=UTC)

# Real teammate accounts, pre-created with the email their 42 OAuth login
# will carry. _upsert_ft_user (app/api/auth.py) matches an incoming login by
# provider_account_id first, then falls back to email - so their first real
# login links to this row instead of creating a fresh "user"-role one, and
# the role assigned here survives (that fallback path never overwrites it).
# avatar_path/display_name are deliberately left at their defaults (None /
# the raw login): a real login only fills avatar_path while it's still
# None, and never touches display_name at all, so anything demo-ish seeded
# here would stay stuck on the real account forever.
TEAM_ACCOUNTS = [
    {"login": "nfenollo", "role": "admin"},
    {"login": "iargence", "role": "admin"},
    {"login": "mzouhir", "role": "admin"},
    {"login": "flomulle", "role": "moderator"},
    {"login": "lmilando", "role": "user"},
]

# How many of the 101 generated listings each of them sells. mzouhir has
# none on purpose - one account with an empty "my listings" tab is part of
# the ask. 5 templates below force their first variant to a specific seller
# instead (subtracted from these counts already) - 3 because they're used
# for a sale, 2 more because a conversation is later built against them
# with a fixed buyer, and a random seller draw could otherwise land on that
# same buyer and trip the "buyer_id <> seller_id" constraint.
SELLER_COUNTS = {
    "nfenollo": 36,
    "iargence": 27,
    "flomulle": 18,
    "lmilando": 15,
    "mzouhir": 0,
}

CATEGORIES = {
    "cat-objet": "Objet",
    "cat-cours": "Cours",
    "cat-covoiturage": "Covoiturage",
    "cat-service": "Service",
    "cat-logement": "Logement",
}

LOCATIONS = {
    "loc-paris": "42 Paris",
    "loc-lyon": "42 Lyon",
    "loc-nice": "42 Nice",
    "loc-mulhouse": "42 Mulhouse",
    "loc-angouleme": "42 Angoulême",
    "loc-perpignan": "42 Perpignan",
    "loc-le-havre": "42 Le Havre",
}
LOCATION_SLUGS = list(LOCATIONS)

# Each template becomes `variants` listings: same product, different seller/
# price/condition/age/popularity - two different people separately selling
# a similar keyboard is exactly what a real marketplace looks like, not a
# duplicate. `image` is a real product photo when one exists in
# front/public/mock/listings, otherwise None (falls back to the category's
# placeholder, same as a listing genuinely posted with no photo).
# `forced_seller`, only on the 3 templates picked for an actual sale below,
# pins that template's first variant to a specific seller instead of the
# shuffled queue, so "the MacBook Pro listing" is always nfenollo's.
LISTING_TEMPLATES = [
    {
        "category": "cat-objet",
        "title": "Clavier mécanique Keychron K2 V2 (RGB, Gateron Brown)",
        "body": "Clavier sans fil / filaire Bluetooth en parfait état. Switches Gateron Brown, "
        "rétroéclairage RGB personnalisable. Livré complet avec boîte d'origine, câble USB-C "
        "et keycaps pour Mac et Windows.",
        "attributes": {
            "brand": "Keychron", "model": "K2 V2", "switch_type": "Gateron Brown",
            "layout": "75% ANSI", "wireless": True, "backlighting": "RGB",
        },
        "image": "/mock/listings/keychron-k2.jpg",
        "base_price": 65, "conditions": ["like_new", "good"], "variants": 3,
        "forced_seller": "iargence",
    },
    {
        "category": "cat-objet",
        "title": 'MacBook Pro 14" M2 Pro (16 Go / 512 Go SSD) Gris Sidéral',
        "body": "MacBook Pro 14 pouces puce Apple M2 Pro, 16 Go de mémoire unifiée, 512 Go SSD. "
        "Batterie à 94% de santé, 85 cycles. Aucune rayure sur l'écran ni sur le châssis. "
        "Facture fournie.",
        "attributes": {
            "brand": "Apple", "screen_size": '14"', "cpu": "Apple M2 Pro", "ram_gb": 16,
            "storage_ssd_gb": 512, "battery_health_pct": 94, "battery_cycles": 85,
            "color": "Space Gray",
        },
        "image": "/mock/listings/macbook-pro-14.jpg",
        "base_price": 1350, "conditions": ["like_new"], "variants": 2,
        "forced_seller": "nfenollo",
    },
    {
        "category": "cat-objet",
        "title": 'Écran Dell UltraSharp 27" 4K (U2723QE IPS Black Hub USB-C)',
        "body": "Moniteur professionnel 4K UHD avec dalle IPS Black (contraste 2000:1). Hub USB-C "
        "avec charge 90W et port Ethernet RJ45 intégré. Zéro pixel mort. Pied réglable en "
        "hauteur et rotation.",
        "attributes": {
            "brand": "Dell", "model": "U2723QE", "screen_size": '27"',
            "resolution": "3840x2160 (4K UHD)", "panel_type": "IPS Black",
            "usb_c_pd_watts": 90, "refresh_rate_hz": 60,
        },
        "image": "/mock/listings/dell-ultrasharp-27.jpg",
        "base_price": 390, "conditions": ["like_new", "good"], "variants": 3,
        "forced_seller": "flomulle",
    },
    {
        "category": "cat-objet",
        "title": "Souris Logitech MX Master 3S Gris Pâle",
        "body": "Souris ergonomique sans fil haut de gamme avec clics silencieux et molette "
        "MagSpeed. Connectivité Bluetooth ou dongle Logi Bolt (fourni). Utilisée environ 4 "
        "mois, état impeccable.",
        "attributes": {
            "brand": "Logitech", "model": "MX Master 3S", "dpi": 8000,
            "connectivity": "Bluetooth / Logi Bolt", "color": "Pale Grey", "silent_clicks": True,
        },
        "image": "/mock/listings/logitech-mx-master-3s.jpg",
        "base_price": 60, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Casque Sony WH-1000XM4 Noir (Réduction de bruit active)",
        "body": "Le casque référence pour coder en silence dans le cluster. Réduction de bruit "
        "active exceptionnelle, autonomie de 30h. Coussinets neufs changés récemment, étui "
        "rigide et adaptateur avion inclus.",
        "attributes": {
            "brand": "Sony", "model": "WH-1000XM4", "anc": True, "battery_life_hours": 30,
            "color": "Black", "multipoint_bluetooth": True,
        },
        "image": "/mock/listings/sony-wh1000xm4.jpg",
        "base_price": 160, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Lenovo ThinkPad T480 (i7-8550U / 32 Go RAM / 512 Go NVMe)",
        "body": "Machine de guerre pour Linux / Arch. Clavier rétroéclairé AZERTY, double batterie "
        "fonctionnelle. Idéal pour les projets C/C++, Docker et virtualisation. Quelques traces "
        "d'usure cosmétiques.",
        "attributes": {
            "brand": "Lenovo", "model": "ThinkPad T480", "cpu": "Intel Core i7-8550U",
            "ram_gb": 32, "storage_ssd_gb": 512, "keyboard_layout": "AZERTY", "dual_battery": True,
        },
        "image": "/mock/listings/lenovo-thinkpad-t480.jpg",
        "base_price": 240, "conditions": ["good", "fair"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Sweat à capuche officiel 42 Paris - Noir Taille L",
        "body": "Sweat officiel de l'école 42 avec logo brodé sur la poitrine. Coton épais de "
        "qualité, intérieur molletonné très confortable.",
        "attributes": {
            "brand": "42 Paris Official", "garment_type": "Hoodie", "size": "L",
            "color": "Black", "material": "100% Cotton Fleece",
        },
        "image": "/mock/listings/sweat-42-paris.jpg",
        "base_price": 30, "conditions": ["new", "like_new"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Nvidia GeForce RTX 3070 Founders Edition 8 Go",
        "body": "Carte graphique Nvidia RTX 3070 FE en excellent état. Utilisée uniquement pour "
        "du gaming casual et un peu d'inférence IA locale (jamais de minage). Températures très "
        "stables.",
        "attributes": {
            "brand": "Nvidia", "model": "RTX 3070 Founders Edition", "vram_gb": 8,
            "bus_interface": "PCIe 4.0 x16", "outputs": ["3x DisplayPort 1.4a", "1x HDMI 2.1"],
        },
        "image": "/mock/listings/geforce-rtx-3070.jpg",
        "base_price": 290, "conditions": ["like_new", "good"], "variants": 3,
        "forced_seller": "iargence",
    },
    {
        "category": "cat-objet",
        "title": "Clavier ergonomique split Corne 36 touches (Wireless Nice!Nano)",
        "body": "Clavier split orthogonal Corne (CRKBD v3) custom. Contrôleurs Nice!Nano v2 sous "
        "ZMK, batteries rechargeables, switches Kailh Choc White tactiles, deux écrans OLED "
        "fonctionnels.",
        "attributes": {
            "kit": "Corne CRKBD v3", "layout": "Split 36 keys column-staggered",
            "controller": "Nice!Nano v2", "firmware": "ZMK", "switches": "Kailh Choc White",
            "oled_screens": 2,
        },
        "image": "/mock/listings/clavier-split-corne.jpg",
        "base_price": 140, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Chaise ergonomique Herman Miller Aeron Remastered - Taille B",
        "body": "Fauteuil ergonomique haut de gamme Herman Miller Aeron taille B (standard). "
        "Support lombaire PostureFit SL, accoudoirs 3D vinyle et bascule avant/arrière. État "
        "proche du neuf.",
        "attributes": {
            "brand": "Herman Miller", "model": "Aeron Remastered", "size": "Size B",
            "lumbar_support": "PostureFit SL", "armrests": "Fully adjustable 3D vinyl",
        },
        "image": "/mock/listings/herman-miller-aeron.jpg",
        "base_price": 850, "conditions": ["like_new", "good"], "variants": 2,
    },
    {
        "category": "cat-objet",
        "title": "Nintendo Switch OLED Blanche + Zelda TOTK",
        "body": "Pack console Switch modèle OLED avec Joy-Cons blancs, dock, câblerie complète et "
        "boîte d'origine. Verre trempé posé dès le premier jour. Jeu Zelda Tears of the Kingdom "
        "inclus en version boîte.",
        "attributes": {
            "brand": "Nintendo", "model": "Switch OLED", "color": "White", "storage_gb": 64,
            "bundled_games": ["Zelda Tears of the Kingdom"],
        },
        "image": "/mock/listings/nintendo-switch-oled.jpg",
        "base_price": 230, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Micro Shure MV7 USB / XLR avec bras articulé",
        "body": "Microphone dynamique inspiré du SM7B, double sortie USB et XLR. Application "
        "ShurePlus MOTIV compatible Windows/Mac/Linux. Vendu avec bras articulé de bureau et "
        "câble USB.",
        "attributes": {
            "brand": "Shure", "model": "MV7", "type": "Dynamic Cardioid",
            "outputs": ["USB Micro-B", "XLR"], "includes_boom_arm": True,
        },
        "image": "/mock/listings/micro-shure-mv7.jpg",
        "base_price": 155, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Raspberry Pi 4 Model B (8 Go RAM) + Boîtier Argon ONE V2 M.2",
        "body": "Kit complet Raspberry Pi 4 avec 8 Go de RAM, boîtier en aluminium Argon ONE "
        "intégrant un port SSD SATA M.2, alimentation officielle 15W et carte MicroSD 64 Go "
        "classe 10.",
        "attributes": {
            "board": "Raspberry Pi 4 Model B", "ram_gb": 8,
            "case_model": "Argon ONE V2 M.2 SATA", "storage_sd_gb": 64, "power_supply_watts": 15,
        },
        "image": "/mock/listings/raspberry-pi-4.jpg",
        "base_price": 85, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": 'Écran LG DualUp 28" (28MQ780-B format vertical 16:18)',
        "body": "Moniteur double écran vertical (résolution SDQHD 2560x2880), idéal pour "
        "afficher du code, un terminal et la documentation simultanément. Bras Ergo LG inclus.",
        "attributes": {
            "brand": "LG", "model": "28MQ780-B DualUp", "screen_size": '27.6"',
            "aspect_ratio": "16:18", "resolution": "2560x2880 (SDQHD)", "panel": "Nano IPS",
            "stand": "LG Ergo Arm",
        },
        "image": "/mock/listings/ecran-lg-dualup.jpg",
        "base_price": 360, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Écouteurs Apple AirPods Pro 2 (Boîtier MagSafe USB-C)",
        "body": "AirPods Pro de 2e génération avec boîtier USB-C. Réduction active du bruit et "
        "mode transparence adaptatif. Nettoyés et désinfectés, embouts silicone de rechange "
        "neufs inclus.",
        "attributes": {
            "brand": "Apple", "model": "AirPods Pro 2", "case_interface": "USB-C MagSafe",
            "anc": True, "adaptive_transparency": True,
        },
        "image": "/mock/listings/airpods-pro-2.jpg",
        "base_price": 150, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Bureau assis-debout électrique FlexiSpot 140x70 cm (Plateau Chêne)",
        "body": "Structure motorisée double moteur silencieux avec panneau de commande mémoire "
        "(4 hauteurs préenregistrées). Plateau finition chêne massif 140x70 cm. À récupérer sur "
        "place.",
        "attributes": {
            "brand": "FlexiSpot", "desktop_size": "140x70 cm", "motors": "Dual motor",
            "memory_presets": 4, "desktop_finish": "Solid Oak",
        },
        "image": "/mock/listings/bureau-assis-debout.jpg",
        "base_price": 210, "conditions": ["like_new", "good"], "variants": 3,
    },
    {
        "category": "cat-objet",
        "title": "Valve Steam Deck LCD 512 Go + Carte SD Samsung 512 Go",
        "body": "Console Steam Deck 512 Go avec écran gravé antireflet d'origine. Vendue avec "
        "étui de transport rigide, chargeur rapide 45W et carte MicroSD Samsung Evo Plus 512 Go.",
        "attributes": {
            "brand": "Valve", "model": "Steam Deck LCD", "internal_ssd_gb": 512,
            "sd_card_gb": 512, "screen_type": "Anti-glare etched glass", "case_included": True,
        },
        "image": "/mock/listings/steam-deck-512.jpg",
        "base_price": 330, "conditions": ["like_new", "good"], "variants": 2,
        "forced_seller": "flomulle",
    },
    {
        "category": "cat-objet",
        "title": "Perceuse à percussion sans fil Bosch 18V",
        "body": "Perceuse à percussion sans fil 18V en parfait état de marche. Livrée avec deux "
        "batteries, chargeur rapide et coffret de transport. Idéale pour le bricolage et les "
        "petits travaux.",
        "attributes": {"brand": "Bosch", "voltage": "18V", "battery_count": 2, "wireless": True},
        "image": None,
        "base_price": 45, "conditions": ["good", "fair"], "variants": 2,
    },
    {
        "category": "cat-cours",
        "title": "Cours de C & algorithmique (Préparation Piscine / Tronc commun)",
        "body": "Étudiant de 42 propose du mentorat et des cours en C : pointeurs, gestion de la "
        "mémoire (malloc/free), listes chaînées et récursivité. Séances sur le campus ou en "
        "visio.",
        "attributes": {
            "subject": "Langage C & Algorithmique", "level": "Piscine & Tronc Commun",
            "format": "Présentiel campus ou Discord", "duration_hours": 1.5,
        },
        "image": "/mock/listings/cours-c-algo.jpg",
        "base_price": 20, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-cours",
        "title": "Tutorat Docker, Nginx & DevOps (Aide aux projets Web)",
        "body": "Accompagnement méthodologique pour vos projets d'infrastructure : reverse proxy "
        "Nginx, conteneurisation Docker multi-services et SSL/TLS. Session pratique de 2h sur le "
        "campus.",
        "attributes": {
            "topic": "Docker, Nginx & DevOps", "format": "Présentiel ou Visio",
            "duration_hours": 2,
        },
        "image": "/mock/listings/tutorat-devops-docker.jpg",
        "base_price": 15, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-cours",
        "title": "Cours de Rust & programmation système",
        "body": "Initiation ou approfondissement Rust : ownership, lifetimes, gestion d'erreurs "
        "et interfaçage avec le C. Idéal en complément des projets système du tronc commun.",
        "attributes": {
            "subject": "Rust & Programmation système", "level": "Tous niveaux",
            "format": "Présentiel campus", "duration_hours": 1.5,
        },
        "image": None,
        "base_price": 18, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-cours",
        "title": "Préparation aux entretiens techniques (style LeetCode)",
        "body": "Sessions d'entraînement aux entretiens techniques : algorithmie, structures de "
        "données, complexité. Retours détaillés et mise en situation chronométrée.",
        "attributes": {
            "subject": "Entretiens techniques", "level": "Fin de cursus / stage",
            "format": "Visio", "duration_hours": 1,
        },
        "image": None,
        "base_price": 25, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-cours",
        "title": "Cours d'anglais technique (préparation TOEFL / entretiens US)",
        "body": "Anglais technique orienté informatique : vocabulaire, présentation de projets, "
        "entretiens en anglais. Préparation TOEFL possible sur plusieurs séances.",
        "attributes": {
            "subject": "Anglais technique", "level": "Tous niveaux", "format": "Visio",
            "duration_hours": 1,
        },
        "image": None,
        "base_price": 22, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-covoiturage",
        "title": "Covoiturage 42 Paris ➔ 42 Lyon (Vendredi soir, 3 places)",
        "body": "Départ vendredi 18h depuis 42 Paris vers 42 Lyon. Trajet direct via l'autoroute "
        "A6, véhicule spacieux avec grand coffre pour bagages et setups informatiques. Frais "
        "d'essence et péage partagés.",
        "attributes": {
            "departure": "42 Paris (Porte de Clichy)", "destination": "42 Lyon",
            "available_seats": 3, "luggage_allowed": True, "departure_time": "Vendredi 18h00",
        },
        "image": "/mock/listings/covoiturage-paris-lyon.jpg",
        "base_price": 25, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-covoiturage",
        "title": "Covoiturage 42 Nice ➔ 42 Angoulême (Week-end, 2 places)",
        "body": "Trajet longue distance pour un week-end de projet en binôme. Départ tôt le "
        "matin, arrêt possible à mi-parcours. Coffre disponible pour setups et bagages.",
        "attributes": {
            "departure": "42 Nice", "destination": "42 Angoulême", "available_seats": 2,
            "luggage_allowed": True, "departure_time": "Samedi 7h00",
        },
        "image": None,
        "base_price": 35, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-covoiturage",
        "title": "Covoiturage quotidien domicile ↔ 42 Paris",
        "body": "Trajet régulier en semaine, place dispo pour un(e) étudiant(e) du même secteur. "
        "Flexible sur les horaires selon les cours ou le rythme cluster.",
        "attributes": {
            "departure": "Banlieue Est", "destination": "42 Paris", "available_seats": 1,
            "luggage_allowed": False, "departure_time": "Variable, 8h-9h",
        },
        "image": None,
        "base_price": 5, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-covoiturage",
        "title": "Covoiturage 42 Mulhouse ➔ 42 Paris (Retour de vacances)",
        "body": "Retour de vacances scolaires, plusieurs places dispo. Départ flexible sur la "
        "journée selon les passagers, coffre pour bagages volumineux.",
        "attributes": {
            "departure": "42 Mulhouse", "destination": "42 Paris", "available_seats": 3,
            "luggage_allowed": True, "departure_time": "Dimanche après-midi",
        },
        "image": None,
        "base_price": 20, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-service",
        "title": "Impression 3D à la demande (PLA / PETG)",
        "body": "Impression de vos pièces/modèles 3D sur imprimante calibrée, PLA ou PETG. Envoi "
        "du fichier STL, devis selon le poids et le temps d'impression. Retrait sur le campus.",
        "attributes": {
            "service_type": "Impression 3D", "materials": ["PLA", "PETG"],
            "max_build_size_mm": "220x220x250", "turnaround_days": 2,
        },
        "image": None,
        "base_price": 12, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-service",
        "title": "Dépannage informatique à domicile (Windows / Linux / macOS)",
        "body": "Installation, réinstallation, dual-boot, virus, configuration réseau... "
        "Intervention sur le campus ou à distance selon le problème.",
        "attributes": {
            "service_type": "Dépannage informatique",
            "platforms": ["Windows", "Linux", "macOS"], "response_time_hours": 24,
        },
        "image": None,
        "base_price": 20, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-service",
        "title": "Montage vidéo pour projets & CV (Premiere / DaVinci Resolve)",
        "body": "Montage et étalonnage de vos vidéos de présentation de projet ou CV vidéo. "
        "Habillage graphique simple inclus. Délai selon la longueur du montage.",
        "attributes": {
            "service_type": "Montage vidéo", "software": ["Premiere Pro", "DaVinci Resolve"],
            "turnaround_days": 4,
        },
        "image": None,
        "base_price": 30, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-service",
        "title": "Retouche et petites réparations de vêtements",
        "body": "Ourlets, boutons, fermetures éclair, petites reprises. Matériel sur place ou "
        "dépôt/retrait sur le campus.",
        "attributes": {"service_type": "Retouche vêtements", "turnaround_days": 3},
        "image": None,
        "base_price": 8, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-logement",
        "title": "Chambre en colocation proche 42 Paris",
        "body": "Chambre meublée dans colocation de 3, proche transports et campus. Charges "
        "comprises, cuisine et salon partagés. Disponible dès le mois prochain.",
        "attributes": {
            "room_type": "Chambre en colocation", "surface_m2": 12,
            "rent_period": "Mensuel, charges comprises", "furnished": True,
        },
        "image": None,
        "base_price": 550, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-logement",
        "title": "Studio meublé proche 42 Lyon",
        "body": "Studio 20m² entièrement meublé et équipé, à 10 minutes à pied du campus. "
        "Idéal pour un étudiant seul, calme et lumineux.",
        "attributes": {
            "room_type": "Studio", "surface_m2": 20,
            "rent_period": "Mensuel, charges comprises", "furnished": True,
        },
        "image": None,
        "base_price": 620, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-logement",
        "title": "Sous-location studio 1 mois (départ en stage)",
        "body": "Sous-location courte durée pendant mon stage, studio meublé proche campus. "
        "Toutes charges et box internet comprises.",
        "attributes": {
            "room_type": "Studio", "surface_m2": 18, "rent_period": "Sous-location 1 mois",
            "furnished": True,
        },
        "image": None,
        "base_price": 480, "conditions": None, "variants": 3,
    },
    {
        "category": "cat-logement",
        "title": "Recherche colocataire - appartement 3 pièces proche 42 Nice",
        "body": "Chambre disponible dans un T3 partagé avec 2 étudiants 42. Ambiance calme, "
        "propre, cuisine équipée. Bail possible dès le mois prochain.",
        "attributes": {
            "room_type": "Chambre en colocation", "surface_m2": 14,
            "rent_period": "Mensuel, charges comprises", "roommates": 2,
        },
        "image": None,
        "base_price": 500, "conditions": None, "variants": 3,
    },
]


def _build_seller_queue(rng: random.Random) -> list[str]:
    queue = [login for login, count in SELLER_COUNTS.items() for _ in range(count)]
    rng.shuffle(queue)
    return queue


async def seed() -> None:
    async with async_session() as session:
        already_seeded = await session.scalar(select(func.count()).select_from(Listing))
        if already_seeded:
            print(f"Seed skipped: {already_seeded} listing(s) already present.")
            return

        users: dict[str, User] = {}
        for account in TEAM_ACCOUNTS:
            user = User(
                email=f"{account['login']}@student.42.fr",
                display_name=account["login"],
                password_hash=None,
                role=account["role"],
            )
            session.add(user)
            users[account["login"]] = user
        await session.flush()

        categories: dict[str, Category] = {}
        for slug, name in CATEGORIES.items():
            category = Category(category_name=name, depth=0, is_leaf=True)
            session.add(category)
            categories[slug] = category
        await session.flush()

        locations: dict[str, Location] = {}
        for slug, name in LOCATIONS.items():
            location = Location(location=name)
            session.add(location)
            locations[slug] = location
        await session.flush()

        rng = random.Random(1337)
        seller_queue = _build_seller_queue(rng)
        listings: list[Listing] = []
        listing_index = 0

        for template in LISTING_TEMPLATES:
            for variant_index in range(template["variants"]):
                if variant_index == 0 and template.get("forced_seller"):
                    seller = users[template["forced_seller"]]
                else:
                    seller = users[seller_queue.pop()]

                price = round(template["base_price"] * rng.uniform(0.85, 1.15) / 5) * 5
                condition = rng.choice(template["conditions"]) if template["conditions"] else None
                days_ago = rng.randint(1, 75)
                published_at = MOCK_NOW - timedelta(days=days_ago, minutes=rng.randint(0, 59))
                view_count = rng.randint(20, 420)
                favorites_count = min(rng.randint(0, view_count // 8), len(users) - 1)

                listing = Listing(
                    seller_id=seller.id,
                    category_id=categories[template["category"]].id,
                    location_id=locations[LOCATION_SLUGS[listing_index % len(LOCATION_SLUGS)]].id,
                    title=template["title"],
                    body=template["body"],
                    price=price,
                    currency="EUR",
                    condition=condition,
                    attributes=template["attributes"],
                    status="active",
                    published_at=published_at,
                    expires_at=published_at + timedelta(days=30),
                    view_count=view_count,
                    created_at=published_at - timedelta(minutes=15),
                    updated_at=published_at,
                )
                session.add(listing)
                await session.flush()

                image_path = template["image"]
                if image_path:
                    image = ListingImage(
                        listing_id=listing.id, storage_path=image_path, position=0,
                        width=800, height=600,
                    )
                    session.add(image)
                    await session.flush()
                    listing.cover_image_id = image.id

                available_favoriters = [u for u in users.values() if u.id != seller.id]
                for favoriter in rng.sample(available_favoriters, favorites_count):
                    session.add(ListingFavorite(user_id=favoriter.id, listing_id=listing.id))

                listings.append(listing)
                listing_index += 1

        def _first(title_part: str) -> Listing:
            return next(listing for listing in listings if title_part in listing.title)

        # --- Concluded sales: conversation -> mark-sold -> review(s), the
        # same steps POST /conversations/{id}/mark-sold and POST /reviews
        # take, so listings.buyer_id and users.rating/rating_count end up
        # exactly as they would from real use. ---

        async def _sell(listing: Listing, buyer: User, days_ago: int) -> Conversation:
            conversation = Conversation(
                listing_id=listing.id, seller_id=listing.seller_id, buyer_id=buyer.id,
            )
            session.add(conversation)
            await session.flush()
            listing.status = ListingStatus.SOLD
            listing.buyer_id = buyer.id
            listing.updated_at = MOCK_NOW - timedelta(days=days_ago)
            return conversation

        def _message(conversation: Conversation, sender: User, body: str, days_ago: float) -> None:
            session.add(
                Message(
                    conversation_id=conversation.id, sender_id=sender.id, body=body,
                    created_at=MOCK_NOW - timedelta(days=days_ago),
                )
            )

        def _review(conversation: Conversation, author: User, subject: User, rating: int, body: str, days_ago: int) -> None:
            session.add(
                Review(
                    conversation_id=conversation.id, author_id=author.id, subject_id=subject.id,
                    rating=rating, body=body, created_at=MOCK_NOW - timedelta(days=days_ago),
                )
            )
            subject.rating += rating
            subject.rating_count += 1

        macbook = _first("MacBook Pro")
        sale_1 = await _sell(macbook, users["iargence"], days_ago=10)
        _message(sale_1, users["iargence"], "Bonjour, le MacBook est toujours dispo ?", days_ago=11)
        _message(sale_1, users["nfenollo"], "Oui, toujours dispo, on peut se voir au bocal demain.", days_ago=10.5)
        _review(
            sale_1, users["iargence"], users["nfenollo"], 5,
            "Vendeur au top, MacBook exactement comme décrit, échange rapide sur le campus.",
            days_ago=9,
        )
        _review(
            sale_1, users["nfenollo"], users["iargence"], 4,
            "Acheteur sérieux, paiement rapide, sans problème.", days_ago=9,
        )

        keychron = _first("Keychron K2")
        sale_2 = await _sell(keychron, users["lmilando"], days_ago=18)
        _message(sale_2, users["lmilando"], "Salut, les switchs sont hot-swappable sur ce modèle ?", days_ago=19)
        _message(sale_2, users["iargence"], "Oui, tu peux changer les switchs sans fer à souder.", days_ago=18.5)
        _review(
            sale_2, users["lmilando"], users["iargence"], 5,
            "Clavier nickel, switchs hot-swap comme annoncé. Merci !", days_ago=17,
        )

        steam_deck = _first("Steam Deck")
        sale_3 = await _sell(steam_deck, users["mzouhir"], days_ago=6)
        _message(sale_3, users["mzouhir"], "Toujours dispo pour ce week-end ?", days_ago=7)
        _message(sale_3, users["flomulle"], "Oui, je te la dépose vendredi soir.", days_ago=6.5)
        _review(
            sale_3, users["mzouhir"], users["flomulle"], 1,
            "Vendeur pas au rendez-vous au premier créneau, console rendue avec l'écran griffé.",
            days_ago=5,
        )

        # --- Friends: one accepted pair, one still pending (an incoming
        # request for flomulle to accept or decline). ---
        session.add(
            Friend(
                requester_id=users["nfenollo"].id, address_id=users["iargence"].id,
                status=FriendStatus.ACCEPTED, responded_at=MOCK_NOW - timedelta(days=20),
            )
        )
        session.add(
            Friend(
                requester_id=users["lmilando"].id, address_id=users["flomulle"].id,
                status=FriendStatus.PENDING, responded_at=None,
            )
        )

        # --- A regular conversation that gets closed by a block, so the
        # unblock-reopens-it fix has something real to exercise. mzouhir
        # never sells (0 in SELLER_COUNTS), so he can never end up on both
        # sides of this listing whoever its seller turns out to be - no
        # need to force that seller like the two below. ---
        blocked_listing = _first("Sweat à capuche")
        blocked_convo = Conversation(
            listing_id=blocked_listing.id, seller_id=blocked_listing.seller_id,
            buyer_id=users["mzouhir"].id, closed=True,
        )
        session.add(blocked_convo)
        await session.flush()
        session.add(
            Message(
                conversation_id=blocked_convo.id, sender_id=users["mzouhir"].id,
                body="Bonjour, le sweat est toujours dispo ?",
                created_at=MOCK_NOW - timedelta(days=4, hours=2),
            )
        )
        session.add(UserBlock(user_blocking=users["mzouhir"].id, user_blocked=blocked_listing.seller_id))

        # --- Two open conversations, one of which hosts a message that
        # gets reported. Both templates below are forced to a fixed seller
        # (see LISTING_TEMPLATES) precisely so that seller can never be the
        # same person as the fixed buyer here. ---
        iargence_listing = _first("Nvidia GeForce RTX 3070")
        report_convo = Conversation(
            listing_id=iargence_listing.id, seller_id=iargence_listing.seller_id,
            buyer_id=users["lmilando"].id,
        )
        session.add(report_convo)
        await session.flush()
        session.add(
            Message(
                conversation_id=report_convo.id, sender_id=users["lmilando"].id,
                body="150€ ou rien, si tu refuses tu vas le regretter au bocal.",
                created_at=MOCK_NOW - timedelta(days=3, hours=1),
            )
        )
        reported_message = await session.scalar(
            select(Message)
            .where(Message.conversation_id == report_convo.id)
            .order_by(Message.id.desc())
        )
        await session.flush()

        flomulle_listing = _first("Écran Dell UltraSharp")
        chat_convo = Conversation(
            listing_id=flomulle_listing.id, seller_id=flomulle_listing.seller_id,
            buyer_id=users["nfenollo"].id,
        )
        session.add(chat_convo)
        await session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=chat_convo.id, sender_id=users["nfenollo"].id,
                    body="Salut, l'écran est toujours disponible ? Le hub USB-C fonctionne bien ?",
                    created_at=MOCK_NOW - timedelta(days=2, hours=5),
                ),
                Message(
                    conversation_id=chat_convo.id, sender_id=flomulle_listing.seller_id,
                    body="Oui, tout fonctionne, je peux te le montrer au cluster si tu veux.",
                    created_at=MOCK_NOW - timedelta(days=2, hours=4),
                ),
            ]
        )

        await session.flush()

        # --- Reports: every target_type, a spread of statuses, all among
        # the 5 real accounts. ---
        reports = [
            Report(
                reporter_id=users["lmilando"].id, target_type="listing", target_id=iargence_listing.id,
                reason="Prix anormalement bas et le vendeur refuse une remise en main propre sur le campus.",
                status=ReportStatus.OPEN, created_at=MOCK_NOW - timedelta(days=3),
            ),
            Report(
                reporter_id=users["mzouhir"].id, target_type="user", target_id=users["lmilando"].id,
                reason="Comportement irrespectueux et messages agressifs répétés sur plusieurs annonces.",
                status=ReportStatus.OPEN, created_at=MOCK_NOW - timedelta(days=2, hours=20),
            ),
            Report(
                reporter_id=iargence_listing.seller_id, target_type="message",
                target_id=reported_message.id,
                reason="Menace à peine déguisée suite à une négociation de prix refusée.",
                status=ReportStatus.OPEN, created_at=MOCK_NOW - timedelta(days=2, hours=23),
            ),
            Report(
                reporter_id=users["flomulle"].id, target_type="review",
                target_id=(await session.scalar(
                    select(Review).where(Review.conversation_id == sale_3.id)
                )).id,
                reason="Avis de vengeance : l'acheteur est bien venu au rendez-vous convenu.",
                status=ReportStatus.OPEN, created_at=MOCK_NOW - timedelta(days=4),
            ),
            Report(
                reporter_id=users["iargence"].id, target_type="listing", target_id=flomulle_listing.id,
                reason="Annonce déjà vendue ailleurs il y a deux semaines mais reste active.",
                status=ReportStatus.CLOSED, created_at=MOCK_NOW - timedelta(days=12),
                closed_at=MOCK_NOW - timedelta(days=11),
            ),
            Report(
                reporter_id=users["nfenollo"].id, target_type="user", target_id=users["mzouhir"].id,
                reason="Signalements multiples et non fondés contre plusieurs vendeurs.",
                status=ReportStatus.RESOLVED, created_at=MOCK_NOW - timedelta(days=15),
                closed_at=MOCK_NOW - timedelta(days=14),
            ),
            Report(
                reporter_id=users["nfenollo"].id, target_type="listing", target_id=_first("Chaise ergonomique").id,
                reason="Photos qui semblent issues d'un catalogue en ligne, pas de l'objet réel.",
                status=ReportStatus.OPEN, created_at=MOCK_NOW - timedelta(days=1, hours=6),
            ),
        ]
        session.add_all(reports)

        await session.commit()
        print(
            f"Seeded {len(TEAM_ACCOUNTS)} team accounts, {len(CATEGORIES)} categories, "
            f"{len(LOCATIONS)} locations, {len(listings)} listings, 3 sales with reviews, "
            f"2 friend rows, 1 block, {len(reports)} reports."
        )


if __name__ == "__main__":
    asyncio.run(seed())
