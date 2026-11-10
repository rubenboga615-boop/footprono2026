"""Noms français des sélections nationales (rapport du testeur du 09/11/2026 : « Scotland »,
« Cyprus », « FYR Macedonia », « Belgium ou nul » dans les paris des joueurs).

Les sélections sont reliées à API-Football par leur numéro (alias « #id »), jamais par leur
nom : les renommer ne change aucun rattachement. Plusieurs écritures d'API-Football pour
un même pays (anciens noms compris) mènent au même nom français.
"""

NATION_NAMES_FR: dict[str, str] = {
    # Europe
    "Albania": "Albanie", "Andorra": "Andorre", "Armenia": "Arménie", "Austria": "Autriche",
    "Azerbaijan": "Azerbaïdjan", "Belarus": "Biélorussie", "Belgium": "Belgique",
    "Bosnia & Herzegovina": "Bosnie-Herzégovine", "Bosnia and Herzegovina": "Bosnie-Herzégovine",
    "Bulgaria": "Bulgarie", "Croatia": "Croatie", "Cyprus": "Chypre",
    "Czech Republic": "Tchéquie", "Czechia": "Tchéquie", "Denmark": "Danemark",
    "England": "Angleterre", "Estonia": "Estonie", "Faroe Islands": "Îles Féroé",
    "Finland": "Finlande", "France": "France", "Georgia": "Géorgie", "Germany": "Allemagne",
    "Gibraltar": "Gibraltar", "Greece": "Grèce", "Hungary": "Hongrie", "Iceland": "Islande",
    "Ireland": "Irlande", "Republic of Ireland": "Irlande", "Israel": "Israël", "Italy": "Italie",
    "Kazakhstan": "Kazakhstan", "Kosovo": "Kosovo", "Latvia": "Lettonie",
    "Liechtenstein": "Liechtenstein", "Lithuania": "Lituanie", "Luxembourg": "Luxembourg",
    "Malta": "Malte", "Moldova": "Moldavie", "Montenegro": "Monténégro",
    "Netherlands": "Pays-Bas", "North Macedonia": "Macédoine du Nord",
    "FYR Macedonia": "Macédoine du Nord", "Macedonia": "Macédoine du Nord",
    "Northern Ireland": "Irlande du Nord", "Norway": "Norvège", "Poland": "Pologne",
    "Portugal": "Portugal", "Romania": "Roumanie", "Russia": "Russie",
    "San Marino": "Saint-Marin", "Scotland": "Écosse", "Serbia": "Serbie",
    "Slovakia": "Slovaquie", "Slovenia": "Slovénie", "Spain": "Espagne", "Sweden": "Suède",
    "Switzerland": "Suisse", "Turkey": "Turquie", "Türkiye": "Turquie", "Ukraine": "Ukraine",
    "Wales": "Pays de Galles",
    # Afrique
    "Algeria": "Algérie", "Angola": "Angola", "Benin": "Bénin", "Botswana": "Botswana",
    "Burkina Faso": "Burkina Faso", "Burundi": "Burundi", "Cameroon": "Cameroun",
    "Cape Verde": "Cap-Vert", "Cape Verde Islands": "Cap-Vert",
    "Central African Republic": "Centrafrique", "Chad": "Tchad", "Comoros": "Comores",
    "Congo": "Congo", "Congo DR": "RD Congo", "DR Congo": "RD Congo", "Djibouti": "Djibouti",
    "Egypt": "Égypte", "Equatorial Guinea": "Guinée équatoriale", "Eritrea": "Érythrée",
    "Eswatini": "Eswatini", "Swaziland": "Eswatini", "Ethiopia": "Éthiopie", "Gabon": "Gabon",
    "Gambia": "Gambie", "Ghana": "Ghana", "Guinea": "Guinée", "Guinea-Bissau": "Guinée-Bissau",
    "Ivory Coast": "Côte d'Ivoire", "Côte d'Ivoire": "Côte d'Ivoire", "Kenya": "Kenya",
    "Lesotho": "Lesotho", "Liberia": "Liberia", "Libya": "Libye", "Madagascar": "Madagascar",
    "Malawi": "Malawi", "Mali": "Mali", "Mauritania": "Mauritanie", "Mauritius": "Maurice",
    "Morocco": "Maroc", "Mozambique": "Mozambique", "Namibia": "Namibie", "Niger": "Niger",
    "Nigeria": "Nigeria", "Rwanda": "Rwanda", "Sao Tome and Principe": "Sao Tomé-et-Principe",
    "Senegal": "Sénégal", "Seychelles": "Seychelles", "Sierra Leone": "Sierra Leone",
    "Somalia": "Somalie", "South Africa": "Afrique du Sud", "South Sudan": "Soudan du Sud",
    "Sudan": "Soudan", "Tanzania": "Tanzanie", "Togo": "Togo", "Tunisia": "Tunisie",
    "Uganda": "Ouganda", "Zambia": "Zambie", "Zimbabwe": "Zimbabwe",
    # Amériques
    "Argentina": "Argentine", "Bolivia": "Bolivie", "Brazil": "Brésil", "Canada": "Canada",
    "Chile": "Chili", "Colombia": "Colombie", "Costa Rica": "Costa Rica", "Cuba": "Cuba",
    "Curacao": "Curaçao", "Curaçao": "Curaçao", "Dominican Republic": "République dominicaine",
    "Ecuador": "Équateur", "El Salvador": "Salvador", "Guatemala": "Guatemala", "Haiti": "Haïti",
    "Honduras": "Honduras", "Jamaica": "Jamaïque", "Mexico": "Mexique",
    "Nicaragua": "Nicaragua", "Panama": "Panama", "Paraguay": "Paraguay", "Peru": "Pérou",
    "Suriname": "Suriname", "Trinidad and Tobago": "Trinité-et-Tobago", "USA": "États-Unis",
    "United States": "États-Unis", "Uruguay": "Uruguay", "Venezuela": "Venezuela",
    # Asie et Océanie
    "Australia": "Australie", "Bahrain": "Bahreïn", "China": "Chine", "China PR": "Chine",
    "India": "Inde", "Indonesia": "Indonésie", "Iran": "Iran", "Iraq": "Irak",
    "Japan": "Japon", "Jordan": "Jordanie", "Korea Republic": "Corée du Sud",
    "South Korea": "Corée du Sud", "Korea DPR": "Corée du Nord", "North Korea": "Corée du Nord",
    "Kuwait": "Koweït", "Kyrgyzstan": "Kirghizistan", "Kyrgyz Republic": "Kirghizistan",
    "Lebanon": "Liban", "Malaysia": "Malaisie", "New Zealand": "Nouvelle-Zélande",
    "Oman": "Oman", "Palestine": "Palestine", "Qatar": "Qatar",
    "Saudi Arabia": "Arabie saoudite", "Syria": "Syrie", "Tajikistan": "Tadjikistan",
    "Thailand": "Thaïlande", "Turkmenistan": "Turkménistan",
    "United Arab Emirates": "Émirats arabes unis", "Uzbekistan": "Ouzbékistan",
    "Vietnam": "Viêt Nam", "Yemen": "Yémen",
}  # fmt: skip


def french_name(name: str) -> str:
    """Nom français d'une sélection ; le nom reçu s'il n'est pas dans la liste."""
    return NATION_NAMES_FR.get(name.strip(), name)
