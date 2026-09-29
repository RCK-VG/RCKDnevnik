# Nadzor učeničkih računala

Modul koji s učeničkih računala prima zapise o aktivnosti (instalirani i
pokrenuti programi, nove mape u AppData, nove ikone, promjena pozadine,
isključivanje mreže) i veže ih uz učenika iz e-Dnevnika.

- **Server** je aplikacija `nadzor` unutar Mali e-Dnevnika (ista baza, isti
  Docker). Zapise vidiš u izborniku **Nadzor**.
- **Klijent** je ova mapa. Na računalu radi kao **servis pod SYSTEM računom**,
  pa ga učenik ne može ugasiti, a ključ i zapisi su u mapi koju ne može ni
  otvoriti. Učeniku se prikazuje samo prozor za prijavu.

> **Važno:** učenik se prijavljuje samo razredom, imenom i prezimenom, bez
> lozinke. Može upisati i kolegu. Zapis zato pokazuje tko se *prijavio*, a ne
> siguran dokaz identiteta: evidencija, ne sigurnosna kontrola.

## Sadržaj mape

| Datoteka | Čemu služi |
|---|---|
| `servis.ps1` | servis (SYSTEM): provjere, slanje, red čekanja, odjava ako se učenik ne prijavi |
| `prozor.ps1`, `pokreni_prozor.vbs` | prozor za prijavu (radi pod učenikom) |
| `instalacija.ps1` | instalacija i uklanjanje (pokreću ga .bat datoteke) |
| `instaliraj.bat` / `deinstaliraj.bat` | to pokrećeš ti, kao administrator |
| `preskoci_procese.txt` | procesi koji se ne javljaju kao "POKRENUTA APLIKACIJA" |
| `config.example.json` | primjer postavki; pravi `config.json` radi se na serveru |
| `config.json`, `rck-ca.crt` | **generiraš ih sam** (sadrže ključ/certifikat, nisu u gitu) |

---

## 1. Postavljanje na serveru (Raspberry Pi), jednom

### 1.1 Ključ i adresa u `.env`

Na Pi-ju, u mapi `~/dnevnik`, otvori `.env` (`nano .env`) i dodaj:

```
NADZOR_API_KEY=<dugi nasumični niz>
NADZOR_HOST=<ime ili IP adresa Pi-ja, npr. alatisssvg.local ili 192.168.1.50>
```

**Ako ruter dodjeljuje adrese sam (DHCP) i Pi nema stalnu adresu**, koristi
ime `<ime-pi-ja>.local` (ime vidiš naredbom `hostname`). Certifikat i
`config.json` tada glase na ime, pa promjena adrese ništa ne kvari. To ime
dodaj i u `ALLOWED_HOSTS`. Prije toga na jednom učeničkom računalu provjeri
da se ime prepoznaje: `ping <ime-pi-ja>.local` mora odgovoriti.

Ključ generiraj naredbom:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ostale postavke imaju razumne zadane vrijednosti (vidi `.env.example`):
`NADZOR_TOKEN_DAYS=7`, `NADZOR_PRIJAVA_MAX_POKUSAJA=30`,
`NADZOR_AKTIVNOST_MINUTA=5`.

### 1.2 Pokretanje (uključuje HTTPS na portu 8443)

```bash
git pull
docker compose up -d --build
```

Uz dnevnik se sad pokreće i **Caddy** koji na `https://<NADZOR_HOST>:8443`
poslužuje aplikaciju s vlastitim (internim) certifikatom. Nastavnici i dalje
mogu koristiti stari `http://<IP>:8080`.

(Ako Pi ima vatrozid `ufw`, otvori port: `sudo ufw allow 8443/tcp`. Ako
naredba `ufw` ne postoji, vatrozida nema i ovo preskačeš.)

### 1.3 Pripremi datoteke za računala

```bash
cd ~/dnevnik
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt klijent/rck-ca.crt
docker compose exec -T web python manage.py nadzor_klijent_config --url https://alatisssvg.local:8443 > klijent/config.json
```

(Umjesto `alatisssvg.local` upiši svoj `NADZOR_HOST`.) Naredba uzme ključ iz
`.env`, pa je ključ na jednom mjestu. Ako ga promijeniš, ponovi ovaj korak i
instalaciju na računalima.

U `config.json` možeš promijeniti:
- `loginTimeoutMinutes` (zadano 2): za koliko minuta se učenik koji se ne
  prijavi odjavljuje iz Windowsa,
- `restrictions` (zadano `true`): ograničenja učeničkog računa (vidi 3.3);
  `false` ih isključuje,
- `pollSeconds` (zadano 60): koliko često se provjerava i šalje.

Zatim cijelu mapu `klijent` kopiraj na USB (npr. `scp -r` na svoje računalo).

### 1.4 Tko vidi zapise

Admin vidi uvijek. Nastavniku daješ pristup u **Django admin → Korisnici →
(nastavnik)**, pri dnu stranice u dijelu "Profile" uključiš kvačicu
**"Smije vidjeti nadzor računala"** i spremiš.

## 2. Instalacija na učeničko računalo

Sve radiš na **administratorskom** računu tog računala.

1. Kopiraj mapu `klijent` (s `config.json` i `rck-ca.crt`) s USB-a na računalo, npr. na radnu površinu.
2. Desni klik na `instaliraj.bat` → **Pokreni kao administrator**.
3. Instalacija ispiše **učeničke račune** koje je pronašla (svi omogućeni
   računi koji NISU administratori, npr. "Učenik" ili "User") i pita
   *Je li popis točan?* Upiši `D` i Enter. Ako nije točan, upiši `N` pa
   imena računa odvojena zarezom.
4. Na kraju piše **Gotovo**. Mapu s USB-a sad možeš obrisati s radne površine.
5. Odjavi se i prijavi na učenički račun: pojavi se prozor za prijavu.

Instalacija:
- kopira servis i `config.json` u `C:\ProgramData\RCKNadzor`, gdje pristup
  imaju **samo SYSTEM i administratori** (učenik mapu ne može ni otvoriti),
- kopira prozor u `C:\ProgramData\RCKNadzorProzor` (učenik ga smije pokrenuti, ne i mijenjati),
- napravi `C:\ProgramData\RCKNadzorRazmjena` preko koje prozor i servis razgovaraju,
- uveze `rck-ca.crt` u pouzdane certifikate računala,
- registrira zadatke **"RCK Nadzor servis"** (SYSTEM, pri pokretanju računala)
  i **"RCK Nadzor prozor"** (pri prijavi učeničkih računa),
- učeničkim računima postavi ograničenja (3.3).

**Administratorski račun ostaje netaknut:** nema prozora, nema ograničenja,
ne bilježi se ništa.

**Nadogradnja** (nova verzija, promjena ključa ili popisa procesa, novi
učenički račun): ponovno pokreni `instaliraj.bat`. Zapisi koji čekaju slanje
se ne gube. **Uklanjanje:** `deinstaliraj.bat` kao administrator (uklanja i
ograničenja).

## 3. Što radi na računalu

### 3.1 Prijava učenika

- Pri prijavi na učenički račun prozor **preko cijelog zaslona** traži
  razred (padajući izbornik sa servera), ime i prezime. Prozor se ne može
  zatvoriti (Alt+F4, minimiziranje) dok prijava ne uspije.
- Ako se učenik **ne prijavi u 2 minute**, servis ga odjavi iz Windowsa i
  zapiše `ODJAVA - NIJE SE PRIJAVIO`. To radi servis, pa pomaže i kad netko
  prozor nekako ugasi.
- Ako upisani učenik ne postoji, prozor javi grešku i pita ponovno.
- **Isti učenik ne može biti prijavljen na dva računala** u isto vrijeme:
  druga prijava se odbija porukom na kojem je računalu već prijavljen.
  Prijava "vrijedi" dok se računalo javlja serveru; ako se računalo ugasi bez
  odjave, nakon 5 minuta (`NADZOR_AKTIVNOST_MINUTA`) može se prijaviti drugdje.
- **Ako server ne radi**, prozor prihvati upisano ime i pusti učenika. Servis
  ga provjeri čim server proradi: ako postoji, zapisi idu pod njega (uz
  `PRIJAVA` s napomenom *naknadno potvrđena*); ako ne postoji, zapisi se
  spremaju kao **neidentificirani** s upisanim imenom.

### 3.2 Što se bilježi

Svakih 60 sekundi servis provjerava i javlja:
- `INSTALIRAN PROGRAM` (registry Uninstall ključevi)
- `NOVA APLIKACIJA (AppData)` (nova mapa u AppData\Roaming, Local ili LocalLow, npr. Roblox)
- `NOVA IKONA/PRECAC` (radna površina učenika i zajednička)
- `PROMJENA POZADINE`
- `POKRENUTA APLIKACIJA` (svaka aplikacija jednom po prijavi; preskaču se programi iz `C:\Windows` i iz `preskoci_procese.txt`)
- `MREŽA ISKLJUČENA` / `MREŽA UKLJUČENA` (provjera svakih 10 sekundi)

Server sam upiše `PRIJAVA` i `ODJAVA`. Uz svaki zapis ide ime računala
(`%COMPUTERNAME%`).

"Novo" znači novo u odnosu na ono što je servis zapamtio za taj učenički
račun. Pri prvoj prijavi na račun samo zapamti postojeće stanje i ništa ne
javlja.

**Ako server ne radi** (ili je mreža isključena), zapisi čekaju u
`C:\ProgramData\RCKNadzor\red.jsonl` i šalju se čim proradi, s točnim
vremenom kad su se dogodili (u tablici piše "na računalu: ...").

Dnevnik servisa (za rješavanje problema, otvara ga administrator):
`C:\ProgramData\RCKNadzor\nadzor.log`.

### 3.3 Ograničenja učeničkog računa

Postavljaju se samo učeničkim računima:
- **Task Manager** je isključen (Ctrl+Shift+Esc javlja da ga je administrator onemogućio),
- sakrivena je **ikona mreže** na programskoj traci,
- isključene su **Postavke i Upravljačka ploča** (tamo se inače gasi Wi-Fi i mijenja pozadina),
- isključen je **Centar za akcije** (brzi gumbi za Wi-Fi i način rada u zrakoplovu).

**Gašenje mreže ne može se potpuno spriječiti:** tipka za Wi-Fi na
tipkovnici prijenosnika, izvlačenje kabela ili naredba `netsh` i dalje rade.
Zato se svako isključivanje **bilježi** (`MREŽA ISKLJUČENA`), a zapisi o
svemu što je učenik radio bez mreže pošalju se kad se mreža vrati.

## 4. Proba bez učeničkog računala (curl, na Pi-ju)

```bash
cd ~/dnevnik
KLJUC=$(grep ^NADZOR_API_KEY .env | cut -d= -f2-)
URL=https://alatisssvg.local:8443/api/nadzor/v1

# popis razreda
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" $URL/razredi/

# prijava učenika -> vrati token
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"razred":"1.C","ime":"Luka","prezime":"Čolić","racunalo":"ROBOTIKA5"}' $URL/prijava/

# jedan zapis (TOKEN iz prethodnog odgovora)
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"token":"TOKEN","racunalo":"ROBOTIKA5","vrsta":"INSTALIRAN PROGRAM","detalji":"Roblox"}' $URL/zapisi/

# odjava
curl --cacert klijent/rck-ca.crt -H "X-API-Key: $KLJUC" -H "Content-Type: application/json" \
  -d '{"token":"TOKEN"}' $URL/odjava/
```

Odgovori: `200` u redu, `201` zapisi primljeni, `400` neispravan zahtjev,
`401` token neispravan, istekao ili odjavljen, `403` krivi ključ, `404`
učenik nije pronađen, `409` učenik je već prijavljen na drugom računalu (ili
dva učenika istog imena u razredu), `429` previše neuspjelih prijava, `503`
ključ nije postavljen na serveru.

Servis i prozor mogu se probati i na običnom računalu, bez instalacije: servis
tada prati trenutnog korisnika, ne odjavljuje ga i ne postavlja ograničenja
(upute su na vrhu `servis.ps1` i `prozor.ps1`). `instalacija.ps1
-SamoProvjera` pokaže koje bi račune nadzirao, bez ikakvih promjena.

## 5. Čuvanje i brisanje zapisa

Zapisi se **ne brišu automatski**. Brišeš ih ručno: Django admin → Nadzor
računala → Zapisi aktivnosti → označi → akcija "Delete". U
`nadzor/models.py` je komentar gdje bi se kasnije dodalo brisanje po roku.

Pazi na prostor na SD kartici: baza raste sa zapisima, a dnevni backup čuva
`BACKUP_KEEP` (zadano 14) cijelih kopija baze. Po potrebi smanji `BACKUP_KEEP`.

## 6. Na što treba paziti

- **Ključ:** učenici ne mogu pročitati `config.json` (mapa je samo za SYSTEM
  i administratore). Ipak, tko zna administratorsku lozinku računala može ga
  pročitati. Ključ omogućuje samo popis razreda, prijavu i slanje zapisa,
  nikad čitanje zapisa.
- **Administratorska lozinka** računala je ono što sve ovo štiti: tko je zna,
  može ugasiti servis i ukloniti ograničenja. Učenici je ne smiju znati.
- **Certifikat:** `rck-ca.crt` je korijenski certifikat Caddyja na Pi-ju i
  računala mu vjeruju. Čuvaj Pi (lozinke, ažuriranja), jer tko preuzme Pi
  mogao bi izdavati certifikate kojima ta računala vjeruju.
- **Obavijest učenicima:** prozor za prijavu kaže da se aktivnost bilježi.
  Neka to škola ima i u pravilima korištenja računala.
