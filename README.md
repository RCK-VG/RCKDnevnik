# Mali e-Dnevnik

Jednostavna web aplikacija za internu evidenciju prisutnosti i bilješki po
nastavnom satu, namijenjena jednom Regionalnom centru kompetentnosti (RCK) i
malom broju nastavnika (5-6). **Ovo nije zamjena za službeni e-Dnevnik** -
samo interni alat za lakše vođenje evidencije i izvoz podataka za školu.

Ovaj README je pisan za osobu koja nije programer. Prati korake redom.

## Sadržaj

1. [Preduvjeti](#1-preduvjeti)
2. [Varijanta A - lokalno u školskoj mreži](#2-varijanta-a---lokalno-u-školskoj-mreži-bez-domene)
3. [Prva prijava i postavljanje](#3-prva-prijava-i-postavljanje)
4. [Demo podaci za isprobavanje](#4-demo-podaci-za-isprobavanje)
5. [Varijanta B - mali VPS s automatskim HTTPS-om](#5-varijanta-b---mali-vps-s-automatskim-https-om)
6. [Ažuriranje aplikacije](#6-ažuriranje-aplikacije)
7. [Sigurnosna kopija (backup) i vraćanje](#7-sigurnosna-kopija-backup-i-vraćanje)
8. [Uloge i ovlasti - kratki pregled](#8-uloge-i-ovlasti---kratki-pregled)
9. [Rješavanje čestih problema](#9-rješavanje-čestih-problema)
10. [Pokretanje automatskih testova](#10-pokretanje-automatskih-testova)
11. [Struktura projekta](#11-struktura-projekta)
12. [Izvan opsega ove verzije](#12-izvan-opsega-ove-verzije)

---

## 1. Preduvjeti

Aplikacija se pokreće pomoću **Dockera** - programa koji cijelu aplikaciju
(Python, bazu podataka, sve ovisnosti) pokreće u izoliranom "kontejneru", bez
potrebe da išta ručno instalirate osim samog Dockera.

- **Windows / Mac:** instalirajte [Docker Desktop](https://www.docker.com/products/docker-desktop/).
  Nakon instalacije potreban je restart računala, zatim pokrenite Docker
  Desktop i prihvatite uvjete korištenja pri prvom pokretanju.
- **Raspberry Pi / Linux server:** instalirajte Docker naredbom:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER
  ```
  Nakon toga se odjavite i ponovno prijavite (ili restartajte uređaj) da
  promjena dopuštenja stupi na snagu.

Provjerite da je instalacija uspjela:
```bash
docker --version
docker compose version
```
Oba bi trebala ispisati broj verzije bez greške.

---

## 2. Varijanta A - lokalno u školskoj mreži (bez domene)

Ova varijanta pokreće aplikaciju na jednom računalu (ili Raspberry Pi-ju)
unutar školske mreže. Ostali nastavnici joj pristupaju preko IP adrese tog
računala, bez potrebe za domenom ili internetom.

### Korak 1: Preuzmite projekt

Kopirajte cijelu projektnu mapu na računalo koje će služiti kao server
(može biti isto računalo na kojem sad čitate ovaj README).

### Korak 2: Podesite postavke

U mapi projekta kopirajte `.env.example` u novu datoteku `.env`:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / Raspberry Pi / Mac
cp .env.example .env
```

Otvorite `.env` u Notepadu (ili bilo kojem uređivaču teksta) i podesite:

- `SECRET_KEY` - postavite neki nasumičan dugačak niz znakova. Možete ga
  generirati naredbom (nakon što jednom pokrenete Docker, vidi dolje), ili
  jednostavno utipkati 40-ak nasumičnih slova/brojeva.
- `ALLOWED_HOSTS` - upišite IP adresu poslužiteljskog računala u mreži,
  npr. `192.168.1.50,localhost`. IP adresu saznajete naredbom `ipconfig`
  (Windows) ili `hostname -I` (Linux/Raspberry Pi).
- `DEBUG=False` - za svakodnevnu upotrebu (ne prikazuje tehničke detalje
  grešaka korisnicima).

### Korak 3: Pokrenite aplikaciju

U mapi projekta pokrenite:

```bash
docker compose up -d --build
```

Prvo pokretanje traje par minuta (Docker preuzima i priprema sve potrebno).
Baza podataka i migracije se postavljaju automatski.

### Korak 4: Otvorite aplikaciju

Na bilo kojem računalu/mobitelu u istoj školskoj mreži otvorite preglednik na:

```
http://<IP-adresa-servera>:8080
```

npr. `http://192.168.1.50:8080`. Ako se ne može spojiti, provjerite da
firewall (Windows Defender Firewall, ili `ufw` na Linuxu/Raspberry Pi-ju)
dopušta dolazne veze na taj port.

> **Već imate nešto drugo pokrenuto na istom uređaju (npr. na Raspberry
> Pi-ju)?** Bez problema - Docker kontejneri su međusobno izolirani, pa je
> dovoljno da svaki program sluša na drugom portu. Broj `8080` u
> `docker-compose.yml` (dio `"8080:8000"`, lijevo od dvotočke) slobodno
> promijenite u bilo koji broj koji na tom uređaju već nije zauzet -
> provjerite naredbom `sudo ss -tulpn` (Linux/Raspberry Pi) prije
> pokretanja.

Nastavite na [poglavlje 3](#3-prva-prijava-i-postavljanje) za izradu admin
računa.

---

## 3. Prva prijava i postavljanje

### Izrada administratorskog računa

Nakon što je aplikacija pokrenuta (`docker compose up -d`), izradite svoj
admin račun:

```bash
docker compose exec web python manage.py createsuperuser
```

Upisat ćete korisničko ime, (opcionalno) e-mail i lozinku. Ovo je vaš
administratorski račun - njime dodajete nastavnike, razrede, predmete i
školske godine.

### Prva prijava

1. Otvorite aplikaciju u pregledniku i prijavite se svojim admin računom.
2. Sustav će odmah tražiti da postavite **novu lozinku** - to je normalno
   ponašanje pri svakoj prvoj prijavi, za sve korisnike.
3. Nakon prijave imate na početnoj stranici gumbe: **Uvoz učenika**,
   **Uvoz predmeta**, **Django admin** i **Preuzmi backup**.

### Osnovno postavljanje podataka

Preko **Django admin** sučelja (`/admin/`) dodajte:

1. **Školsku godinu** (npr. "2025./2026.", označite je aktivnom).
2. **Predmete** (ili ih uvezite - vidi niže).
3. **Razrede** (npr. "1.a") vezane uz tu školsku godinu, po želji s
   razrednikom.
4. **Korisnike** (nastavnike) - stvorite im račun s privremenom lozinkom;
   pri prvoj prijavi će je sami promijeniti. Ostavite kvačicu "staff"
   isključenu za obične nastavnike (samo administratori trebaju "staff").

### Uvoz učenika i predmeta

Umjesto ručnog unosa, na početnoj stranici (kao admin) koristite:

- **Uvoz učenika** - CSV ili Excel datoteka sa stupcima `razred, prezime,
  ime, IP, PP` (IP/PP upišite kao "da"/"ne", prazno = ne). Sustav prije
  spremanja prikaže pregled što će se dodati/ažurirati/preskočiti.
- **Uvoz predmeta** - CSV ili Excel s jednim stupcem naziva predmeta.

Hrvatski dijakritički znakovi (č, ć, š, ž, đ) se ispravno prepoznaju bez
obzira dolazi li datoteka iz novijeg ili starijeg Excela.

---

## 4. Demo podaci za isprobavanje

Za testiranje aplikacije prije prave upotrebe, možete napuniti bazu
**izmišljenim** demo podacima (učenici, nastavnici, razredi, predmeti):

```bash
docker compose exec web python manage.py seed_demo
```

Naredba ispiše popis izmišljenih nastavničkih korisničkih imena i
zajedničku privremenu lozinku. **Nikad ne pokrećite ovu naredbu na bazi
koja već sadrži prave podatke** o pravim učenicima - koristite je samo na
praznoj/testnoj bazi.

---

## 5. Varijanta B - mali VPS s automatskim HTTPS-om

Ova varijanta pokreće aplikaciju na malom vanjskom poslužitelju (VPS),
dostupnom preko interneta, s automatskim besplatnim HTTPS certifikatom
(putem [Caddyja](https://caddyserver.com/)). Domena je opcionalna - bez nje
aplikacija radi preko običnog HTTP-a na IP adresi VPS-a.

### Korak 1: Nabavite VPS

Bilo koji jeftini VPS (npr. Hetzner, DigitalOcean, ili domaći pružatelj) s
Ubuntu/Debian sustavom je dovoljan (1 CPU, 1-2 GB RAM-a je više nego dovoljno
za 5-6 korisnika).

### Korak 2: Instalirajte Docker na VPS-u

Prijavite se na VPS preko SSH-a i instalirajte Docker (vidi [poglavlje 1](#1-preduvjeti)).

### Korak 3: Prebacite projekt na VPS

Kopirajte projektnu mapu na VPS (npr. preko `git clone` ako je u
repozitoriju, ili `scp -r` sa svog računala).

### Korak 4: (Opcionalno) Usmjerite domenu

Ako imate domenu, kod svog registratora domene dodajte **A zapis** koji
`dnevnik.vasaskola.hr` usmjerava na IP adresu VPS-a. Bez ovog koraka Caddy
ne može automatski izdati HTTPS certifikat (Let's Encrypt zahtijeva pravu
domenu, ne radi za gole IP adrese).

### Korak 5: Podesite `.env`

Isto kao u [koraku 2 varijante A](#korak-2-podesite-postavke), uz dodatno:

- `ALLOWED_HOSTS=dnevnik.vasaskola.hr` (ili IP adresa VPS-a ako nemate domenu)
- `DOMAIN=dnevnik.vasaskola.hr` (ili ostavite `localhost` ako nemate domenu)
- `SECURE_SSL_REDIRECT=True` (samo ako koristite pravu domenu s HTTPS-om)
- `CSRF_TRUSTED_ORIGINS=https://dnevnik.vasaskola.hr` (isto, samo uz domenu)

### Korak 6: Otvorite potrebne portove

Na VPS-u dopustite dolazni promet na portove 80 i 443, npr.:
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```
(ili kroz kontrolnu ploču vašeg pružatelja VPS-a, ako koristi vlastiti
firewall).

### Korak 7: Pokrenite

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy će automatski zatražiti i obnavljati HTTPS certifikat (može potrajati
minutu prvi put). Otvorite `https://dnevnik.vasaskola.hr` (ili
`http://<IP-VPS-a>` ako nemate domenu).

Napravite admin račun kao u [poglavlju 3](#3-prva-prijava-i-postavljanje),
ali s dodatkom `-f docker-compose.prod.yml`:
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

> **Napomena:** u svim daljnjim naredbama u ovom README-u, ako koristite
> Varijantu B, dodajte `-f docker-compose.prod.yml` odmah iza `docker
> compose` u svakoj naredbi.

---

## 6. Ažuriranje aplikacije

Kad dobijete noviju verziju koda (npr. novu funkcionalnost):

1. Zamijenite datoteke projekta novima (ili `git pull` ako koristite git).
2. Ponovno izgradite i pokrenite:
   ```bash
   docker compose up -d --build
   ```
   (uz `-f docker-compose.prod.yml` za Varijantu B).

Migracije baze podataka se pokreću **automatski** pri svakom pokretanju,
tako da ne morate ništa ručno raditi s bazom.

---

## 7. Sigurnosna kopija (backup) i vraćanje

### Automatski dnevni backup

Poseban servis unutar Dockera svaki dan napravi kopiju baze podataka u
mapu `backups/` (na poslužitelju, izvan Docker kontejnera - vidljivo i
dostupno i ako Docker prestane raditi). Čuva se zadnjih `BACKUP_KEEP`
kopija (zadano 14, podesivo u `.env`), starije se automatski brišu.

### Ručni backup na zahtjev

Prijavljeni administrator na početnoj stranici ima gumb **"Preuzmi
backup"** - klikom se odmah izrađuje i preuzima svježa kopija baze
podataka (`.sqlite3` datoteka) na vaše računalo.

### Vraćanje iz backupa

Ako trebate vratiti bazu na stanje iz neke sigurnosne kopije:

1. Zaustavite aplikaciju:
   ```bash
   docker compose down
   ```
2. Zamijenite trenutnu bazu odabranom kopijom iz mape `backups/`:
   ```bash
   # Linux / Mac / Raspberry Pi
   cp backups/db_20260115_030000_000000.sqlite3 data/db.sqlite3

   # Windows (PowerShell)
   Copy-Item backups\db_20260115_030000_000000.sqlite3 data\db.sqlite3 -Force
   ```
3. Ponovno pokrenite aplikaciju:
   ```bash
   docker compose up -d
   ```

> Napomena: automatski backup i gumb "Preuzmi backup" rade samo uz zadanu
> SQLite bazu. Ako ste prešli na PostgreSQL (preko `DATABASE_URL`), za
> sigurnosne kopije koristite `pg_dump`.

---

## 8. Uloge i ovlasti - kratki pregled

- **Administrator** (osoba koja postavlja sustav) - vidi i uređuje sve:
  korisnike, razrede, učenike, predmete, sve satove i sve bilješke; jedini
  ima pristup Django admin sučelju, potpunom izvozu i backupu.
- **Nastavnik** - vidi sve razrede/učenike/satove/bilješke (bez
  ograničenja), ali **uređuje samo svoje satove i vlastite bilješke**.
  Samo razrednik razreda (ili admin) smije označiti izostanak kao
  opravdan/neopravdan.
- Svaki korisnik pri prvoj prijavi mora sam postaviti novu lozinku.
- Nakon 5 pogrešnih pokušaja prijave (podesivo u `.env`), račun je
  privremeno blokiran 15 minuta.

---

## 9. Rješavanje čestih problema

**"Port je već zauzet" / aplikacija se ne pokreće**
Netko drugi (drugi program, ili drugi Docker kontejner) na tom uređaju već
koristi port 8080. U `docker-compose.yml` promijenite lijevu stranu u retku
`"8080:8000"` u bilo koji slobodan broj, npr. `"8090:8000"`, zatim
pristupajte na `:8090`. Slobodne portove provjerite naredbom
`sudo ss -tulpn` (Linux/Raspberry Pi) ili `netstat -ano` (Windows).

**Zaboravljena admin lozinka**
```bash
docker compose exec web python manage.py changepassword <korisnicko-ime>
```

**Ne mogu pristupiti aplikaciji s drugog računala u mreži**
Provjerite da koristite stvarnu IP adresu servera (ne `localhost`), i da
firewall na poslužiteljskom računalu dopušta dolazne veze na port koji ste
postavili u `docker-compose.yml` (zadano 8080).

**Kod Varijante B, HTTPS certifikat se ne generira**
Provjerite da je DNS zapis domene stvarno usmjeren na IP adresu VPS-a
(može potrajati do nekoliko sati nakon promjene), te da su portovi 80 i
443 doista otvoreni prema internetu.

**Slučajno sam pokrenuo/la `seed_demo` na bazi s pravim podacima**
`seed_demo` samo dodaje nove izmišljene zapise (ne briše postojeće), ali
najbolje je odmah vratiti bazu iz zadnjeg backupa (vidi poglavlje 7) ako
se to dogodi.

**Kako vidim što se događa ako nešto ne radi (logovi)**
```bash
docker compose logs -f web
```

---

## 10. Pokretanje automatskih testova

Unutar Dockera:
```bash
docker compose exec web python manage.py test dnevnik
```

Lokalno bez Dockera (ako imate Python instaliran i virtualno okruženje u
`.venv`, kako je korišteno tijekom razvoja):
```bash
.venv\Scripts\python.exe manage.py test dnevnik   # Windows
.venv/bin/python manage.py test dnevnik           # Linux/Mac
```

Testovi pokrivaju: ovlasti (nastavnik ne može uređivati tuđe satove ni
bilješke, samo razrednik/admin postavlja opravdano/neopravdano), unos
prisutnosti bez duplikata, ispravno rukovanje hrvatskim znakovima pri
uvozu, te sadržaj izvoza (autor bilješke, tema sata, sažetak izostanaka).

---

## 11. Struktura projekta

```
config/             Django postavke (settings.py, urls.py)
dnevnik/             Glavna aplikacija
  models.py          Podatkovni model (razredi, učenici, satovi, prisutnost...)
  views_*.py         Ekrani (prijava, sat, pregled, izvoz, uvoz, backup)
  forms.py           Forme
  exports.py         Izrada Excel/CSV izvoza
  backup.py          Izrada sigurnosne kopije baze
  imports.py         Uvoz učenika/predmeta iz CSV/Excel
  tests/             Automatski testovi
  management/commands/  seed_demo, backup_db
templates/           HTML predlošci (Bootstrap + HTMX + Alpine.js)
Dockerfile           Slika za pokretanje aplikacije
docker-compose.yml       Varijanta A (lokalna mreža)
docker-compose.prod.yml  Varijanta B (VPS + Caddy + HTTPS)
Caddyfile            Postavke automatskog HTTPS-a
.env.example         Predložak konfiguracije (kopirati u .env)
```

---

## 12. Izvan opsega ove verzije

Sljedeće namjerno nije uključeno u verziju 1, u skladu s dogovorenim
opsegom: dodjela predmeta pojedinim nastavnicima, redni broj sata unutar
dana, rad bez interneta (offline), ocjenjivanje, pristup roditeljima,
integracija sa CARNET e-Dnevnikom, slanje automatskih obavijesti.
