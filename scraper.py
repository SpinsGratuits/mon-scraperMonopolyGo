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

# Dictionnaire de traduction des mois (français vers numérique)
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

# Client de contournement Cloudflare
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

print("[1/2] Analyse de la page d'accueil d'Infinity Area...")
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
    
    # ÉTAPE 1 : Identification de tous les articles contenant les dés quotidiens
    articles_du_jour = []
    for link in soup.find_all("a", href=True):
        href_article = link["href"].strip()
        texte_article = link.get_text().strip().lower()
        
        # CORRECTION : Ciblage élargi aux structures d'URL réelles (/article/...)
        if "des-gratuits-monopoly-go" in href_article or "des-gratuits" in texte_article:
            if href_article.startswith("/"):
                href_article = base_site + href_article
            elif not href_article.startswith("http"):
                continue
                
            # Extraction propre de la date (Ex: du-1-octobre-2026)
            match_date = re.search(r'(\d{1,2})\s*[-_\s]\s*([a-zæœéûou]+)\s*[-_\s]\s*(\d{4})', texte_article + href_article)
            if match_date:
                jour = match_date.group(1).zfill(2)
                nom_mois = match_date.group(2)
                annee = match_date.group(3)
                
                num_mois = mois_fr_to_num.get(nom_mois, "01")
                date_article_str = f"{jour}/{num_mois}/{annee}"
                
                try:
                    date_objet = datetime.strptime(date_article_str, "%d/%m/%Y")
                    # On évite les doublons d'articles dans notre liste de parcours
                    if date_objet >= limite_conservation and href_article not in [a[0] for a in articles_du_jour]:
                        articles_du_jour.append((href_article, date_article_str))
                except:
                    pass

    # ÉTAPE 2 : Parcours profond des sous-pages collectées
    print(f"[2/2] {len(articles_du_jour)} pages d'articles valides repérées. Extraction des liens de dés...")
    
    for url_article, date_parution_str in articles_du_jour:
        try:
            print(f" -> Récupération de l'article : {url_article}")
            res_article = scraper.get(url_article, timeout=10)
            if res_article.status_code != 200:
                continue
                
            # Analyse complète de la page de l'article
            soup_article = BeautifulSoup(res_article.text, "html.parser")
            
            for link_dd in soup_article.find_all("a", href=True):
                href_de = link_dd["href"].strip()
                
                # Validation des domaines officiels ou raccourcis autorisés
                keywords = ["scope.ly", "monopolygo", "adj.st", "t.co", "bit.ly"]
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
                            "recompense": anciens_liens[href].get("recompense", type_recompense) if href_de in anciens_liens else type_recompense, 
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
            
            # Temporisation anti-bannissement (1 seconde)
            time.sleep(1)
            
        except Exception as e:
            print(f"[Erreur] Problème sur la page {url_article} : {e}")

    # Fallback de secours si l'accès réseau échoue pendant le crawling
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI CHRONOLOGIQUE PAR DATE DE PARUTION ---
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT EN FICHIER JSON ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} mis à jour ({len(json_data)} liens indexés chronologiquement).")
            
else:
    print(f"[Erreur] Échec d'accès à la page racine (Code {status_code}).")
