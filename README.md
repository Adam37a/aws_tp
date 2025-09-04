1) Prérequis
Système : Ubuntu 22.04+ (ok sur Ubuntu 24.04 EC2).
Python : 3.10+ (3.12 sur Ubuntu 24.04).
Accès AWS (recommandé) : IAM Role attaché à l’EC2 avec permissions S3 minimales

2) Installation :
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3-pip python3-venv  # si nécessaire
  mkdir -p ~/myproject && cd ~/myproject
   python3 -m venv venv
  source venv/bin/activate

pip install --upgrade pip
pip install requests beautifulsoup4 tqdm boto3

3) Utilisation
Place le script dans le dossier et exécute :

python scrape_pokemon_images_to_s3.py \
  --s3-bucket <TON_BUCKET> \
  --s3-prefix pokemon \
  --delay 0.5


  Résultat : 
  <img width="1247" height="497" alt="image" src="https://github.com/user-attachments/assets/014fa86f-65e8-4f54-87a8-9b4af3e26b3c" />

  <img width="1915" height="872" alt="image" src="https://github.com/user-attachments/assets/334f8ada-83eb-42d7-9793-7d384390f355" />

  exemple d'url public :
  https://tp-stockage-pokemon.s3.eu-west-3.amazonaws.com/pokemon/Generation+I/0001Bulbasaur.png

  


  


  

