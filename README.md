

1) Prérequis
Système : Ubuntu 22.04+ (ok sur Ubuntu 24.04 EC2).
Python : 3.10+ (3.12 sur Ubuntu 24.04).
Accès AWS (recommandé) : IAM Role attaché à l’EC2 avec permissions S3 minimales

2) Installation :
```
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv  # si nécessaire
mkdir -p ~/myproject && cd ~/myproject
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install requests beautifulsoup4 tqdm boto3
```
3) Utilisation

Place le script dans le dossier et exécute :
```
python scrape_pokemon_images_to_s3.py \
  --s3-bucket <TON_BUCKET> \
  --s3-prefix pokemon \
  --delay 0.5
  ```


  Résultat : 
  <img width="1247" height="497" alt="image" src="https://github.com/user-attachments/assets/014fa86f-65e8-4f54-87a8-9b4af3e26b3c" />

  <img width="1915" height="872" alt="image" src="https://github.com/user-attachments/assets/334f8ada-83eb-42d7-9793-7d384390f355" />

  exemple d'url public :
  https://tp-stockage-pokemon.s3.eu-west-3.amazonaws.com/pokemon/Generation+I/0001Bulbasaur.png


  Choix technique : 
-Journalisation simple
Messages explicites en cas d’échec d’upload avec l’URL source et la clé S3 cible.

-tqdm
Barre de progression par génération, avec le dernier fichier traité → visibilité sur l’avancement.

-Erreurs HTTP
404 sur l’original : on ignore l’image (le site peut ne pas avoir l’original pour certaines miniatures).
429/5xx : retries automatiques via Retry.

   Sécurité & gouvernance AWS:
- IAM Role sur l’EC2 (recommandé)
Évite de gérer des clés statiques sur l’instance.
Permissions minimales (principes de moindre privilège) : s3:ListBucket, s3:PutObject, s3:PutObjectTagging uniquement sur le bucket cible (et éventuellement un préfixe).

-Lecture publique des objets
Réalisée via bucket policy (et non via ACLs), aligné avec “Bucket owner enforced”/ACLs désactivées.
Possibilité de restreindre à un préfixe (ex. pokemon/*) pour plus de finesse.

-Aucune écriture locale
Réduit l’empreinte disque et les risques de fuite de données locales (sur le script python)

  


  


  

