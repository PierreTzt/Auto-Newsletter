import feedparser
from openai import OpenAI
import os
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from datetime import datetime, timedelta
import subprocess
import shutil
import time

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

# Récupérer les variables d'environnement
openai_api_key = os.getenv("OPENAI_API_KEY")
feed_url = os.getenv("FEED_URL")
git_token = os.getenv("GIT_TOKEN")

# Initialisation du client OpenAI
client = OpenAI(api_key=openai_api_key)

# Fonction pour récupérer les articles d'un flux RSS
def get_rss_feed(feed_url):
    return feedparser.parse(feed_url)

# Fonction pour filtrer les articles publiés dans les dernières 24 heures
def filter_recent_articles(entries):
    recent_entries = []
    now = datetime.now()
    for entry in entries:
        # Convertir la date de publication de l'article en objet datetime
        published = datetime(*entry.published_parsed[:6])
        # Comparer avec l'heure actuelle moins 24 heures
        if now - timedelta(hours=24) <= published <= now:
            recent_entries.append(entry)
    return recent_entries

# Fonction pour analyser les titres avec l'API OpenAI et sélectionner les plus engageants
def analyze_titles_with_openai(titles, client, limit, temperature):
    prompt = (
        f"Voici quelques titres d'articles :\n{titles}\n"
        f"Veuillez sélectionner les {limit} meilleurs qui généreraient le plus d'engagement sur LinkedIn."
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en identification de contenu engageant pour LinkedIn."},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature
    )
    
    selected_titles = response.choices[0].message.content.strip().split("\n")
    return [title.strip().replace("**", "").replace('"', '') for title in selected_titles if title.strip()]

# Fonction pour générer un titre pour la newsletter
def generate_newsletter_title(client, top_titles):
    prompt = (
        f"Générez un titre percutant et engageant pour une newsletter basée sur les articles suivants :\n{', '.join(top_titles)}. "
        "Le titre doit être concis, captivant et adapté à un public professionnel."
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en rédaction de titres accrocheurs pour des newsletters professionnelles, capables de capter l'attention tout en restant pertinents pour une audience professionnelle."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    # Ajouter la date du jour à la fin du titre
    date_today = datetime.now().strftime("%d/%m/%Y")
    title = response.choices[0].message.content.strip().replace('**', '').replace('"', '')
    return f"{title} - {date_today}"

# Fonction pour récupérer les articles et choisir la miniature avec correspondance floue
def get_top_articles_with_thumbnails(feed, top_titles, threshold=60):  # Réduire le seuil à 60
    selected_articles = []
    cleaned_top_titles = [title.strip().lower() for title in top_titles]
    
    for entry in feed.entries:
        entry_title_cleaned = entry.title.strip().lower()
        for top_title in cleaned_top_titles:
            if fuzz.ratio(entry_title_cleaned, top_title) >= threshold:
                thumbnail = entry.get("media_thumbnail", entry.get("media_content", [{}]))[0].get("url", "")
                selected_articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "thumbnail": thumbnail
                })
                break  # Sortir de la boucle une fois qu'une correspondance est trouvée
    return selected_articles

# Fonction pour générer la liste des articles sous forme de HTML
def generate_article_list(top_articles):
    article_list = ""
    for article in top_articles:
        article_list += f"<li class='article'><a href='{article['link']}'>{article['title']}</a></li>\n"
    return article_list

# Fonction pour générer l'introduction avec l'API OpenAI
def generate_introduction(client):
    prompt = (
        "Rédigez une introduction engageante et concise pour une newsletter quotidienne. "
        "L'introduction doit évoquer les thèmes généraux des articles sans les énumérer directement, "
        "et donner envie au lecteur de découvrir le contenu en détail. "
        "Utilisez un ton professionnel avec une touche d'enthousiasme."
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en rédaction de newsletters impactantes, spécialisées pour un public professionnel sur LinkedIn. Votre mission est de captiver l'attention dès les premiers mots, tout en offrant une valeur immédiate aux lecteurs."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )
    
    return response.choices[0].message.content.strip().replace("**", "").replace("\n", "<br>")

# Fonction pour générer la conclusion avec l'API OpenAI
def generate_conclusion(client):
    prompt = "Rédigez une conclusion légèrement fun concise de 70 mots pour une newsletter LinkedIn. Cette conclusion doit encourager les lecteurs à commenter, partager et s'engager avec le contenu, en mettant l'accent sur l'importance de leur participation pour enrichir la discussion. Si vous utilisez des hashtags, ils doivent être en anglais et apparaître sur une ligne séparée."
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en rédaction de newsletters convaincantes et engageantes, spécialement conçues pour un public professionnel sur LinkedIn. Votre mission est de créer des conclusions qui non seulement résonnent avec les lecteurs, mais les incitent aussi à interagir activement."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )
    
    return response.choices[0].message.content.strip().replace("**", "").replace("\n", "<br>")

# Fonction pour générer le post LinkedIn avec une liste à puces et des emojis générés dynamiquement
def generate_linkedin_post(client, top_titles):
    prompt = (
        "Générez un post LinkedIn court (maximum 150 mots) pour promouvoir une newsletter quotidienne contenant les articles suivants :\n"
        f"{', '.join(top_titles)}.\n"
        "Pour chaque titre, choisissez un emoji pertinent (qui doit être devant le titre) et présentez-le sous forme de liste à puces pour un post LinkedIn engageant. Ajoutez des hashtags en anglais à la fin."
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[
            {"role": "system", "content": "Vous êtes un expert en gestion des médias sociaux, spécialisé dans la création de posts LinkedIn engageants et stratégiques. Votre objectif est de promouvoir efficacement des contenus tout en maximisant l'interaction et la portée."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )
    
    return response.choices[0].message.content.strip().replace("**", "")

# Fonction pour générer la page HTML avec les boutons de copie et le post LinkedIn
def generate_html_page(newsletter_title, introduction, article_list_html, conclusion, linkedin_post):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{newsletter_title}</title>
        <style>
            :root {{
              --kaki-green: #005C53;
              --pomme-green: #9FC131;
              --infinite-green: #042904;
              --background-light: #f4f4f4;
              --background-dark: #e6e6e6;
              --content-width: 1200px;
            }}

            body {{
              font-family: "Luciole", sans-serif;
              font-size: 14px;
              margin: 0;
              background-color: var(--background-light);
              color: var(--infinite-green);
              line-height: 1.6;
              display: flex;
              justify-content: center;
              padding: 20px;
            }}

            .container {{
              max-width: var(--content-width);
              width: 100%;
              background-color: white;
              border-radius: 10px;
              box-shadow: 0 0 15px rgba(0, 0, 0, 0.1);
              padding: 20px;
              overflow: hidden;
            }}

            h1 {{
              color: var(--kaki-green);
              font-size: 2em;
              margin-bottom: 20px;
              text-align: center;
            }}

            .intro {{
              background-color: var(--background-dark);
              padding: 15px;
              border-radius: 8px;
              margin-bottom: 20px;
              text-align: center;
            }}

            .articles {{
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
              gap: 20px;
              margin-bottom: 30px;
            }}

            .article {{
              background-color: var(--background-dark);
              padding: 20px;
              border-radius: 10px;
              box-shadow: 0 5px 10px rgba(0, 0, 0, 0.1);
              transition: transform 0.3s ease;
            }}

            .article:hover {{
              transform: translateY(-5px);
            }}

            .article a {{
              color: var(--infinite-green);
              text-decoration: none;
              font-weight: bold;
              font-size: 1.1em;
              display: block;
              margin-bottom: 10px;
            }}

            .article a:hover {{
              text-decoration: underline;
            }}

            .conclusion {{
              background-color: var(--background-dark);
              padding: 15px;
              border-radius: 8px;
              margin-bottom: 20px;
              text-align: center;
            }}

            .linkedin-section {{
              margin-top: 40px;
              text-align: center;
            }}

            .linkedin-section textarea {{
              width: 100%;
              height: 150px;
              padding: 10px;
              font-size: 16px;
              border-radius: 5px;
              border: 1px solid var(--infinite-green);
            }}

            .linkedin-section .button {{
              display: inline-block;
              padding: 10px 20px;
              margin-top: 20px;
              font-size: 16px;
              color: white;
              background-color: var(--kaki-green);
              border: none;
              border-radius: 5px;
              cursor: pointer;
              text-align: center;
            }}

            .linkedin-section .button:hover {{
              background-color: var(--pomme-green);
            }}

            .button-container {{
              display: flex;
              justify-content: space-between;
              margin-top: 20px;
            }}

            @media (max-width: 768px) {{
              body {{
                padding: 10px;
              }}

              h1 {{
                font-size: 1.5em;
              }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 id="titleText">{newsletter_title}</h1>
            <div class="button-container">
                <button class="linkedin-section button" onclick="copyTitle()">Copier le Titre</button>
                <button class="linkedin-section button" onclick="copyContent()">Copier Intro + Articles + Conclusion</button>
            </div>
            <div id="contentToCopy">
                <div class="intro">
                    <p>{introduction}</p>
                </div>
                <div class="articles">
                    {article_list_html}
                </div>
                <div class="conclusion">
                    <p>{conclusion}</p>
                </div>
            </div>
            <div class="linkedin-section">
                <h2>Post LinkedIn</h2>
                <textarea id="linkedinPost" readonly>{linkedin_post}</textarea>
                <button class="linkedin-section button" onclick="copyPost()">Copier le Post LinkedIn</button>
            </div>
        </div>
        <script>
            function copyTitle() {{
                var titleText = document.getElementById("titleText").innerText;
                var textarea = document.createElement("textarea");
                textarea.value = titleText;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
            }}

            function copyContent() {{
                var range = document.createRange();
                range.selectNode(document.getElementById("contentToCopy"));
                window.getSelection().removeAllRanges(); // Clear current selection
                window.getSelection().addRange(range); // Select the content
                document.execCommand("copy");
                window.getSelection().removeAllRanges(); // Unselect after copy
            }}

            function copyPost() {{
                var postText = document.getElementById("linkedinPost").value;
                var textarea = document.createElement("textarea");
                textarea.value = postText;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
            }}
        </script>
    </body>
    </html>
    """

    # Générer le nom de fichier basé sur la date du jour
    date_today = datetime.now().strftime("%d%m%Y")
    
    # Chemin où le fichier sera enregistré
    save_path = "newsletter"
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    # Nom complet du fichier avec le chemin
    filename = os.path.join(save_path, f"{date_today}.html")

    # Enregistrer le contenu HTML dans un fichier
    with open(filename, "w", encoding="utf-8") as file:
        file.write(html_content)

# Fonction pour générer la page HTML pour le blog sans boutons ni post LinkedIn
def generate_blog_html_page(newsletter_title, introduction, article_list_html, conclusion):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{newsletter_title}</title>
        <style>
            :root {{
              --kaki-green: #005C53;
              --pomme-green: #9FC131;
              --infinite-green: #042904;
              --background-light: #f4f4f4;
              --background-dark: #e6e6e6;
              --content-width: 1200px;
            }}

            body {{
              font-family: "Luciole", sans-serif;
              font-size: 14px;
              margin: 0;
              background-color: var(--background-light);
              color: var(--infinite-green);
              line-height: 1.6;
              display: flex;
              justify-content: center;
              padding: 20px;
            }}

            .container {{
              max-width: var(--content-width);
              width: 100%;
              background-color: white;
              border-radius: 10px;
              box-shadow: 0 0 15px rgba(0, 0, 0, 0.1);
              padding: 20px;
              overflow: hidden;
            }}

            h1 {{
              color: var(--kaki-green);
              font-size: 2em;
              margin-bottom: 20px;
              text-align: center;
            }}

            .intro {{
              background-color: var(--background-dark);
              padding: 15px;
              border-radius: 8px;
              margin-bottom: 20px;
              text-align: center;
            }}

            .articles {{
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
              gap: 20px;
              margin-bottom: 30px;
            }}

            .article {{
              background-color: var(--background-dark);
              padding: 20px;
              border-radius: 10px;
              box-shadow: 0 5px 10px rgba(0, 0, 0, 0.1);
              transition: transform 0.3s ease;
            }}

            .article:hover {{
              transform: translateY(-5px);
            }}

            .article a {{
              color: var(--infinite-green);
              text-decoration: none;
              font-weight: bold;
              font-size: 1.1em;
              display: block;
              margin-bottom: 10px;
            }}

            .article a:hover {{
              text-decoration: underline;
            }}

            .conclusion {{
              background-color: var(--background-dark);
              padding: 15px;
              border-radius: 8px;
              margin-bottom: 20px;
              text-align: center;
            }}

            @media (max-width: 768px) {{
              body {{
                padding: 10px;
              }}

              h1 {{
                font-size: 1.5em;
              }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{newsletter_title}</h1>
            <div class="intro">
                <p>{introduction}</p>
            </div>
            <div class="articles">
                {article_list_html}
            </div>
            <div class="conclusion">
                <p>{conclusion}</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Générer le nom de fichier basé sur la date du jour
    date_today = datetime.now().strftime("%d%m%Y")
    
    # Chemin où le fichier sera enregistré
    save_path = "C:\\Users\\pierr\\OneDrive\\Documents\\GitHub\\CV-2024\\newsletter-blog"
    if not os.path.exists(save_path):
        os.makedirs(save_path)
    
    # Nom complet du fichier avec le chemin
    filename = os.path.join(save_path, f"{date_today}.html")

    # Enregistrer le contenu HTML dans un fichier
    with open(filename, "w", encoding="utf-8") as file:
        file.write(html_content)

def git_push():
    try:
        # Chemin où les fichiers HTML sont générés et doivent être ajoutés au dépôt Git
        repo_path = "C:/Users/pierr/OneDrive/Documents/GitHub/CV-2024/newsletter-blog"
        
        # Ajouter les fichiers générés au suivi Git (dans le dépôt local)
        subprocess.run(["git", "add", f"{repo_path}/*.html"], cwd="C:/Users/pierr/OneDrive/Documents/GitHub/CV-2024", check=True)

        # Effectuer un commit avec un message
        commit_message = f"Auto-generated newsletter for {datetime.now().strftime('%d/%m/%Y')}"
        subprocess.run(["git", "commit", "-m", commit_message], cwd="C:/Users/pierr/OneDrive/Documents/GitHub/CV-2024", check=True)

        # Attendre quelques secondes pour s'assurer que tout est en place
        time.sleep(5)

        # Configurer l'URL distante avec le token
        git_remote_url = f"https://{git_token}@github.com/PierreTzt/CV-2024.git"
        subprocess.run(["git", "push", git_remote_url, "main"], cwd="C:/Users/pierr/OneDrive/Documents/GitHub/CV-2024", check=True)

        print("Les fichiers ont été poussés avec succès sur le dépôt distant.")

    except subprocess.CalledProcessError as e:
        print(f"Une erreur s'est produite lors de l'exécution de la commande Git : {e}")

# Récupération du flux RSS
feed = get_rss_feed(feed_url)

# Filtrer les articles publiés dans les dernières 24 heures
recent_entries = filter_recent_articles(feed.entries)

# Vérifier si des articles récents ont été récupérés
if len(recent_entries) == 0:
    print("Aucun article récent trouvé dans les dernières 24 heures.")
else:
    titles = [entry.title for entry in recent_entries]

    # Analyse des titres avec OpenAI pour la newsletter complète
    top_titles_for_newsletter = analyze_titles_with_openai("\n".join(titles), client, limit=15, temperature=0.7)

    # Génération d'un titre pour la newsletter
    newsletter_title = generate_newsletter_title(client, top_titles_for_newsletter)

    # Sélection des articles et miniatures avec correspondance floue
    top_articles = get_top_articles_with_thumbnails(feed, top_titles_for_newsletter)

    if len(top_articles) == 0:
        print("Aucun article correspondant trouvé pour les titres sélectionnés.")
    else:
        # Génération de la liste d'articles cliquables pour la newsletter
        article_list_html = generate_article_list(top_articles)

        # Génération du texte d'introduction, de conclusion et du post LinkedIn
        introduction = generate_introduction(client)
        conclusion = generate_conclusion(client)
        linkedin_post = generate_linkedin_post(client, top_titles_for_newsletter[:5])

        # Génération de la page HTML avec les boutons et le post LinkedIn
        generate_html_page(newsletter_title, introduction, article_list_html, conclusion, linkedin_post)

        # Génération de la page HTML pour le blog sans les boutons ni le post LinkedIn
        generate_blog_html_page(newsletter_title, introduction, article_list_html, conclusion)
        
        # Exécuter le push vers le dépôt Git
        git_push()
