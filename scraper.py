import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
url = "https://mosttechs.com/how-to-get-credits-in-bingo-blitz/"
filename = "scrapbingoblitz.json"

# Dictionnaire complet incluant toutes les variantes et abréviations de mois
mois_en_to_num = {
    "january": "01", "jan": "01", "januray": "01",
    "february": "02", "feb": "02", "february ": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08", "augest": "08",
    "september": "09", "sep": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12"
}

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")

# MODIFICATION : Extension de la conservation de l'historique à 15 jours glissants
limite_conservation = now - timedelta(days=15)

# --- 2. CHARGEMENT & NETTOYAGE DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        try:
                            date_objet = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
                            # Filtrage basé sur le nouveau seuil des 15 jours
                            if date_objet >= limite_conservation:
                                anciens_liens[item["lienurl"]] = item
                        except:
                            anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# Client de contournement anti-bot Cloudflare
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

try:
    response = scraper.get(url, timeout=15)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"[Erreur] Connexion impossible : {e}")

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    json_data = []
    liens_visites_session = set()  # Optimisation de recherche anti-doublon
    
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    # --- 3. PARCOURS DE LA STRUCTURE TEXTUELLE ---
    current_date_str = now.strftime("%d/%m/%Y")  # Valeur par défaut
    
    for element in entry_content.find_all(["p", "ul", "ol", "strong"]):
        text = element.get_text().strip().lower()
        
        # Détection d'une ligne de date isolée
        match_date = re.search(r'(\d{1,2})\s+([a-z]{3,})\s+(\d{4})', text)
        if match_date:
            jour = match_date.group(1).zfill(2)
            nom_mois = match_date.group(2)
            annee = match_date.group(3)
                
            num_mois = mois_en_to_num.get(nom_mois, "01")
            current_date_str = f"{jour}/{num_mois}/{annee}"
            continue  
            
        links = element.find_all("a", href=True)
        for link in links:
            href = link["href"].strip()
            
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            keywords = ["bingoblitz", "playtika", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    if date_objet < limite_conservation:
                        continue  
                except:
                    pass
                
                if href in liens_visites_session:
                    continue
                liens_visites_session.add(href)
                
                type_recompense = "Credits gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION : PRIORITÉ AU PLUS RÉCENT ---
                if href in anciens_liens:
                    try:
                        ancienne_date = datetime.strptime(anciens_liens[href].get("date", ""), "%d/%m/%Y")
                        nouvelle_date = datetime.strptime(current_date_str, "%d/%m/%Y")
                        
                        # Si le site internet republie un ancien lien à une date plus récente
                        if nouvelle_date > ancienne_date:
                            date_scraping_finale = date_now_str
                            date_scraping1_finale = f"{current_date_str} @ {heure_actuelle_str}"
                            date_finale = current_date_str
                            heure_finale = heure_actuelle_str
                            badge_actuel = "NEW"
                        else:
                            # Sinon, on conserve les informations de l'historique
                            date_scraping_finale = anciens_liens[href].get("date_scraping", date_now_str)
                            date_scraping1_finale = anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}")
                            date_finale = anciens_liens[href].get("date", current_date_str)
                            heure_finale = anciens_liens[href].get("heure", "00:00")
                            
                            # Contrôle standard des 6 heures pour le badge NEW
                            date_premier_scraping = datetime.strptime(date_scraping_finale, "%d/%m/%Y @ %H:%M")
                            badge_actuel = "NEW" if now - date_premier_scraping < timedelta(hours=6) else ""
                    except:
                        date_scraping_finale = anciens_liens[href].get("date_scraping", date_now_str)
                        date_scraping1_finale = anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}")
                        date_finale = current_date_str
                        heure_finale = anciens_liens[href].get("heure", "00:00")
                        badge_actuel = anciens_liens[href].get("badge", "")

                    json_data.append({
                        "date_scraping": date_scraping_finale, 
                        "date_scraping1": date_scraping1_finale,
                        "date": date_finale,  
                        "heure": heure_finale,
                        "recompense": anciens_liens[href].get("recompense", type_recompense), 
                        "lienurl": href,
                        "badge": badge_actuel
                    })
                else:
                    # VRAI NOUVEAU LIEN : Première fois qu'on le croise
                    date_scraping1_combinee = f"{current_date_str} @ {heure_actuelle_str}"
                    json_data.append({
                        "date_scraping": date_now_str, 
                        "date_scraping1": date_scraping1_combinee,
                        "date": current_date_str,  
                        "heure": heure_actuelle_str,
                        "recompense": type_recompense, 
                        "lienurl": href,
                        "badge": "NEW" 
                    })

    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI CHRONOLOGIQUE PAR DATE DE PARUTION ---
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Bingo Blitz {filename} mis à jour ({len(json_data)} liens valides sur 15 jours).")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
