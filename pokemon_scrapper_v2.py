#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper Bulbapedia -> Upload direct S3 par génération
Source: https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_by_National_Pok%C3%A9dex_number
Dépendances: requests, beautifulsoup4, tqdm, boto3
Installation: pip install requests beautifulsoup4 tqdm boto3
Usage:
  python scrape_pokemon_images_to_s3.py --s3-bucket tp-stockage-pokemon --s3-prefix pokemon --delay 0.5
"""

import os
import re
import time
import argparse
import mimetypes
from urllib.parse import urljoin, urlparse, quote
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm
import boto3
from botocore.exceptions import ClientError

BASE_URL = "https://bulbapedia.bulbagarden.net/wiki/List_of_Pok%C3%A9mon_by_National_Pok%C3%A9dex_number"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PokemonImageScraper/1.1; +https://example.org/educational)"
}

GENERATION_HEADING_RE = re.compile(r"^\s*Generation\s+[IVXLCDM]+", re.I)

def make_http_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

def fetch_soup(session, url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def is_thumbnail(url_path: str) -> bool:
    # Bulbapedia thumbs look like /media/upload/thumb/<hash>/<filename>/<width>px-<filename>
    return "/thumb/" in url_path

def to_full_image_url(thumb_url: str) -> str:
    """
    Convertit une URL miniature Bulbapedia/Archives -> URL d'image originale.
    Ex:
      https://archives.bulbagarden.net/media/upload/thumb/3/39/001Bulbasaur.png/120px-001Bulbasaur.png
    ->  https://archives.bulbagarden.net/media/upload/3/39/001Bulbasaur.png
    """
    parsed = urlparse(thumb_url)
    path = parsed.path
    if not is_thumbnail(path):
        return thumb_url
    parts = path.split("/")
    try:
        idx = parts.index("thumb")
    except ValueError:
        return thumb_url
    if len(parts) >= idx + 4:
        new_parts = parts[:idx] + parts[idx+1:-1]  # enlève "thumb" et le segment taille
        new_path = "/".join(new_parts)
        return parsed._replace(path=new_path).geturl()
    return thumb_url

def sanitize_component(name: str) -> str:
    # Nettoyage léger pour dossiers/clefs S3
    name = re.sub(r"[\\:*?\"<>|]", "_", name.strip())
    name = name.replace("..", "_")
    return name

def heading_text(h_tag) -> str:
    return h_tag.get_text(" ", strip=True)

def iter_generation_sections(soup: BeautifulSoup):
    """Yield (titre_generation, [tables HTML])"""
    headings = []
    for tag in soup.find_all(["h2", "h3", "h4"]):
        span = tag.find(["span", "div"], class_="mw-headline")
        label = span.get_text(" ", strip=True) if span else tag.get_text(" ", strip=True)
        if GENERATION_HEADING_RE.match(label or ""):
            headings.append(tag)

    for i, h in enumerate(headings):
        gen_title = heading_text(h)
        tables = []
        walker = h.find_next_sibling()
        while walker and walker not in headings and not (
            walker.name in ["h2", "h3", "h4"] and walker.find(class_="mw-headline")
        ):
            if walker.name == "table":
                tables.append(walker)
            walker = walker.find_next_sibling()
        if tables:
            yield gen_title, tables

def extract_image_urls_from_table(table):
    urls = []
    for img in table.find_all("img"):
        src = img.get("data-src") or img.get("src")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urljoin("https://bulbapedia.bulbagarden.net", src)
        urls.append(src)
    return urls

def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NotFound", "NoSuchKey"):
            return False
        raise

def upload_image_from_url(session, s3, url: str, bucket: str, key: str, delay: float = 0.5) -> bool:
    """Télécharge l'image (stream) et la pousse sur S3 sous 'key'."""
    if object_exists(s3, bucket, key):
        # déjà présent => on saute
        return True

    with session.get(url, stream=True, timeout=60) as r:
        if r.status_code == 404:
            return False
        r.raise_for_status()
        # Déterminer un Content-Type correct
        ctype = r.headers.get("Content-Type")
        if not ctype:
            ctype = mimetypes.guess_type(urlparse(url).path)[0] or "application/octet-stream"
        extra = {"ContentType": ctype}
        # Uploader en streaming
        r.raw.decode_content = True  # gère gzip/deflate si présent
        s3.upload_fileobj(r.raw, bucket, key, ExtraArgs=extra)

    if delay > 0:
        time.sleep(delay)
    return True

def build_s3_key(prefix: str, generation: str, filename: str) -> str:
    parts = []
    if prefix:
        parts.append(prefix.strip("/"))
    parts.append(sanitize_component(generation))
    parts.append(filename)
    return "/".join(parts)

def public_http_url(bucket: str, key: str) -> str:
    # On essaie d'utiliser la région des variables d'env si dispo (sinon endpoint global)
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if region:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key)}"
    return f"https://{bucket}.s3.amazonaws.com/{quote(key)}"

def main():
    parser = argparse.ArgumentParser(description="Uploader directement les images Bulbapedia vers S3, classées par génération.")
    parser.add_argument("--s3-bucket", required=True, help="Nom du bucket S3 de destination (obligatoire)")
    parser.add_argument("--s3-prefix", default="pokemon", help="Préfixe/‘dossier’ S3 (ex: pokemon). Vide = racine du bucket")
    parser.add_argument("--delay", type=float, default=0.5, help="Délai (s) entre uploads pour rester poli")
    parser.add_argument("--max-per-gen", type=int, default=0, help="Limiter le nombre d'images par génération (0 = illimité)")
    args = parser.parse_args()

    http = make_http_session()
    s3 = boto3.client("s3")

    print("→ Chargement de la page liste…")
    soup = fetch_soup(http, BASE_URL)

    total_uploaded = 0

    for gen_title, tables in iter_generation_sections(soup):
        # Collecter toutes les URLs d'images de la génération
        thumb_urls = []
        for t in tables:
            thumb_urls.extend(extract_image_urls_from_table(t))

        # Convertir les miniatures vers images originales quand possible
        full_urls = []
        for u in thumb_urls:
            try:
                parsed = urlparse(u)
                if parsed.netloc.endswith("bulbagarden.net") or parsed.netloc.endswith("archives.bulbagarden.net"):
                    full_urls.append(to_full_image_url(u))
                else:
                    full_urls.append(u)
            except Exception:
                full_urls.append(u)

        # Unicité + filtrer par extension d'image
        seen = set()
        urls = []
        for u in full_urls:
            if u not in seen:
                seen.add(u)
                path = urlparse(u).path
                if re.search(r"\.(png|jpg|jpeg|gif|webp)$", path, re.I):
                    urls.append(u)

        print(f"\n→ {gen_title}: {len(urls)} images détectées")
        if args.max_per_gen and len(urls) > args.max_per_gen:
            urls = urls[:args.max_per_gen]

        # Upload S3
        pbar = tqdm(urls, desc=f"Upload S3 {gen_title}", unit="img")
        for url in pbar:
            filename = os.path.basename(urlparse(url).path)
            key = build_s3_key(args.s3_prefix, gen_title, filename)
            try:
                ok = upload_image_from_url(http, s3, url, args.s3_bucket, key, delay=args.delay)
                if ok:
                    total_uploaded += 1
                    pbar.set_postfix_str(filename)
            except Exception as e:
                print(f"[ERREUR] {url} -> s3://{args.s3_bucket}/{key} : {e}")

    print(f"\n✓ Terminé. Images présentes dans s3://{args.s3_bucket}/{args.s3_prefix or ''}")
    # Exemple d’URL publique (si bucket policy OK) :
    example_key = build_s3_key(args.s3_prefix, "Generation I", "001Bulbasaur.png")
    print("Exemple URL publique (si lecture publique activée) :")
    print("  " + public_http_url(args.s3_bucket, example_key))

if __name__ == "__main__":
    main()
