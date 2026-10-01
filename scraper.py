import json
import os
import re
import time
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
url_principale = "https://infinity-area.com/jeux/monopoly-go"
base_site = "https://infinity-area.com"
filename = "scrapmonopolygo.json"

# Traduction française complète pour la reconstruction des objets Date
mois_fr_to_num = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04", "mai": "05", "juin": "06",
    "juillet": "07", "août": "08", "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
}

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")
limite_conservation = now - timedelta(days=6)

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
                            if date_objet >= limite_conservation:
                                anciens_liens[item["lienurl"]] = item
                        except:
                            anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# Client anti-bot Cloudflare
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

print("[1/2] Analyse globale de la page d'accueil d'Infinity Area...")
try:
    response = scraper.get(url_principale, timeout=15)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"[Erreur] Connexion impossible : {e}")

json_data = []
liens_visites_session = set()

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    
    # ÉTAPE 1 : Identification de tous les liens d'articles sur la page
    articles_du_jour = []
    for link in soup.find_all("a", href=True):
        href_article = link["href"].strip()
        
        # Vérification si le lien correspond bien à un article (contient /article/)
        if "/article/" in href_article and "lancers-de-des-gratuits" in href_article:
            if href_article.startswith("/"):
                href_article = base_site + href_article
                
            # CORRECTION DE LA REGEX : Nettoyage du "1,2trace" accidentel pour restaurer le scan historique
            match_date = re.search(r'du-(\d{1,2})-([a-zæœéûou‡]+)-(\d{4})', href_article.lower())
            if match_date:
                jour = match_date.group(1).zfill(2)
                nom_mois = match_date.group(2)
                annee = match_date.group(3)
                
                num_mois = mois_fr_to_num.get(nom_mois, "01")
                date_article_str = f"{jour}/{num_mois}/{annee}"
                
                try:
                    date_objet = datetime.strptime(date_article_str, "%d/%m/%Y")
                    # Ajout de l'article s'il est récent et non dupliqué
                    if date_objet >= limite_conservation and href_article not in [a for a, _ in articles_du_jour]:
                        articles_du_jour.append((href_article, date_article_str))
                except:
                    pass

    # ÉTAPE 2 : Extraction en profondeur des liens de récompense
    print(f"[2/2] {len(articles_du_jour)} articles récents valides localisés. Extraction des liens profonds...")
    
    for url_article, date_parution_str in articles_du_jour:
        try:
            print(f" -> Ouverture de l'article : {url_article}")
            res_article = scraper.get(url_article, timeout=10)
            if res_article.status_code != 200:
                continue
                
            soup_article = BeautifulSoup(res_article.text, "html.parser")
            
            # Recherche de tous les liens hypertextes sortants de l'article
            for link_de in soup_article.find_all("a", href=True):
                href_de = link_de["href"].strip()
                
                # Exclusion stricte des liens Reddit
                if "reddit" in href_de.lower():
                    continue
                
                # Mots-clés de redirection officiels Monopoly Go
                keywords = ["scope.ly", "monopolygo", "adj.st", "mply.io", "t.co", "bit.ly"]
                if any(key in href_de.lower() for key in keywords):
                    
                    if href_de in liens_visites_session:
                        continue
                    liens_visites_session.add(href_de)
                    
                    type_recompense = "Dés gratuits"
                    
                    # --- GESTION DU BADGE NEW (CONSERVATION 6 HEURES) ---
                    if href_de in anciens_liens:
                        date_premier_scraping_str = anciens_liens[href_de].get("date_scraping", date_now_str)
                        badge_actuel = ""
                        
                        try:
                            date_premier_scraping = datetime.strptime(date_premier_scraping_str, "%d/%m/%Y @ %H:%M")
                            if now - date_premier_scraping < timedelta(hours=6):
                                badge_actuel = "NEW"
                        except:
                            badge_actuel = anciens_liens[href_de].get("badge", "")

                        json_data.append({
                            "date_scraping": date_premier_scraping_str, 
                            "date_scraping1": anciens_liens[href_de].get("date_scraping1", f"{date_parution_str} @ {heure_actuelle_str}"),
                            "date": date_parution_str,  
                            "heure": anciens_liens[href_de].get("heure", "00:00"),
                            "recompense": anciens_liens[href_de].get("recompense", type_recompense), 
                            "lienurl": href_de,
                            "badge": badge_actuel
                        })
                    else:
                        # Nouveau lien trouvé
                        date_scraping1_combinee = f"{date_parution_str} @ {heure_actuelle_str}"
                        json_data.append({
                            "date_scraping": date_now_str, 
                            "date_scraping1": date_scraping1_combinee,
                            "date": date_parution_str,  
                            "heure": heure_actuelle_str,
                            "recompense": type_recompense, 
                            "lienurl": href_de,
                            "badge": "NEW" 
                        })
            
            # Pause de politesse d'une seconde pour préserver le serveur
            time.sleep(1)
            
        except Exception as e:
            print(f"[Erreur] Échec de l'analyse profonde sur {url_article} : {e}")

    # Sécurité Fallback : Conserver l'historique propre si le site n'a temporairement rien renvoyé
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI CHRONOLOGIQUE ---
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} synchronisé avec succès ({len(json_data)} liens valides indexés).")
            
else:
    print(f"[Erreur] Échec de la communication réseau (Code {status_code}).")
