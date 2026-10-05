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
| `preskoci_domene.txt` | domene koje se ne javljaju kao "POSJEĆENA STRANICA" (pozadinski promet) |
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
- `logSites` (zadano `true`): bilježenje posjećenih domena (vidi 3.2);
  `false` ga isključuje,
- `autoUpdate` (zadano `true`): samo-ažuriranje klijenta (vidi „Automatsko
  ažuriranje" niže); `false` ga isključuje,
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

## Automatsko ažuriranje (bez USB-a za buduće promjene)

USB treba **samo prvi put**, da servis uopće dođe na računalo. Nakon toga se
klijent ažurira sam: server nudi trenutne datoteke, a servis ih svakih pola
sata provjeri i, ako su se promijenile, preuzme i ponovno se pokrene (za manje
od minute). Tako ispravak skripte ili dodavanje domene/procesa u popis ne
treba raznositi na 50 računala.

**Kako objaviti promjenu** (na Pi-ju):

```bash
cd ~/dnevnik
git pull                     # ili ručno izmijeni datoteku u klijent/
docker compose up -d         # ako je promjena došla kroz git pull
```

Datoteke iz `klijent/` server čita kroz spoj koji je već namješten u
`docker-compose.yml` (`./klijent:/app/klijent:ro`, samo čitanje), pa nakon
`git pull` nije potreban `--build`. Sva računala povuku novu verziju u roku
od pola sata (ili pri sljedećem paljenju).

**Što se ažurira:** `servis.ps1`, `prozor.ps1`, `pokreni_prozor.vbs`,
`preskoci_procese.txt`, `preskoci_domene.txt`. Svaka datoteka se provjerava
kontrolnom sumom (SHA-256) prije zamjene; server nikad ne šalje `config.json`
ni certifikat.

**Što se NE ažurira ovako** (za to i dalje treba `instaliraj.bat` na računalu):
- `config.json` (adresa servera, ključ, postavke) - lokalan je,
- popis učeničkih računa i njihova ograničenja,
- sami zadaci u Task Scheduleru.

**Sigurnost:** ovo znači da server (Pi) može poslati kod koji se na računalima
izvodi kao SYSTEM. Datoteke stižu s Pi-ja preko HTTPS-a kojem računala vjeruju,
pa je ključno **čuvati Pi** (lozinke, ažuriranja) - kao i za certifikat (vidi
zadnje poglavlje). Tko preuzme Pi, ionako već ima tu moć. Ako želiš zamrznuti
verziju na nekom računalu, u njegov `config.json` stavi `"autoUpdate": false`.

## 3. Što radi na računalu

### 3.1 Prijava učenika

- Pri prijavi na učenički račun prozor **preko cijelog zaslona** traži
  razred (padajući izbornik sa servera), ime i prezime. Prozor se ne može
  zatvoriti (Alt+F4, minimiziranje) dok prijava ne uspije.
- Ako se učenik **ne prijavi u 2 minute**, servis ga odjavi iz Windowsa i
  zapiše `ODJAVA - NIJE SE PRIJAVIO`. To radi servis, pa pomaže i kad netko
  prozor nekako ugasi.
- **Nakon ponovnog pokretanja računala** tražila se nova prijava (stara više
  ne vrijedi), a **nakon buđenja iz mirovanja** (sleep) prozor se automatski
  ponovno pojavi i traži prijavu (zapis `MIROVANJE - PONOVNA PRIJAVA`). Prozor
  radi cijelu prijavu i sam se pokazuje/skriva po potrebi.
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

Servis provjerava i javlja (teže provjere svakih 60 s, a zapisi se šalju na
server svakih ~15 s, pa brzo postanu vidljivi):
- `INSTALIRAN PROGRAM` (registry Uninstall ključevi)
- `NOVA APLIKACIJA (AppData)` (nova mapa u AppData\Roaming, Local ili LocalLow, npr. Roblox)
- `NOVA IKONA/PRECAC` (radna površina učenika i zajednička)
- `PROMJENA POZADINE`
- `POKRENUTA APLIKACIJA` (svaka aplikacija jednom po prijavi; preskaču se programi iz `C:\Windows` i iz `preskoci_procese.txt`)
- `POSJEĆENA STRANICA` (domena koju je računalo posjetilo, npr. `poki.com`; vidi niže)
- `MREŽA ISKLJUČENA` / `MREŽA UKLJUČENA` (provjera svakih 10 sekundi)

Server sam upiše `PRIJAVA` i `ODJAVA`. Uz svaki zapis ide ime računala
(`%COMPUTERNAME%`).

**Posjećene stranice** (`POSJEĆENA STRANICA`) čitaju se iz DNS predmemorije
računala (koje je domene računalo razriješilo), a **ne** iz povijesti
preglednika. Zato:
- radi za **svaki preglednik** (Chrome, Edge, Firefox...) i za sve igre u
  pregledniku, bez ovisnosti o pregledniku,
- bilježi se **domena** (npr. `poki.com`, `now.gg`, `coolmathgames.com`), a
  **ne puna adresa** stranice ni sadržaj,
- pozadinski promet Windowsa, antivirusa i CDN-ova preskače se popisom
  `preskoci_domene.txt` (uredi ga po potrebi; nakon izmjene pokreni
  `instaliraj.bat` ponovno),
- domena se javi jednom po prijavi. Rijetko posjećena stranica čiji "rok
  trajanja" (DNS TTL) istekne prije provjere može promaknuti - ovo je
  evidencija, ne potpuni zapis prometa.

Da bi se stranice iz preglednika uopće vidjele, servis natjera preglednik da
imena traži **preko Windowsa**: u Chromeu i Edgeu isključi "Secure DNS" (DoH) i
njihov vlastiti DNS resolver, a u Firefoxu DoH. Inače preglednik razrješava
imena sam i nadzor ih ne vidi. Promjena vrijedi **nakon što se preglednik
ponovno pokrene**. Deinstalacija vraća te postavke na zadano. (Za odmah, bez
čekanja, postoji i `iskljuci_secure_dns.bat` - npr. za pokretanje preko Veyona.)

Da popis bude čitljiv i koristan:
- bilježi se **osnovna domena** (`roblox.com`), ne svaka poddomena posebno;
- **reklamne i tracking domene se preskaču.** Dva popisa: `preskoci_domene.txt`
  (manji, u gitu - tu dodaješ vlastite iznimke) i `reklamne_domene.txt` (veliki
  gotovi popis koji se **sam preuzima na Pi-ju**; vidi niže). Jedna stranica
  inače povuče stotine takvih, pa bez toga zapisi budu nečitljivi;
- ista domena javlja se ponovno tek nakon `siteRepeatMinutes` (zadano 5 min),
  da se vidi i povratak na stranicu, a da se ne ponavlja u nedogled.

Bilježenje stranica isključuje se s `"logSites": false` u `config.json`.

**Veliki popis reklama (`reklamne_domene.txt`)** preuzima se gotov s interneta
pa ga ne moraš održavati. Osvježava ga `backup` usluga **svaki dan sama**; ručno:

```bash
docker compose exec web python manage.py nadzor_reklame
```

Popis se sprema u `klijent/` na Pi-ju (nije u gitu) i računala ga povuku
auto-updateom. Poklapanje ide po **punom imenu** (npr. `ads.nekistie.com` se
preskače, ali obična `nekistie.com` i dalje prolazi), pa se prave stranice ne
gube. Za drugi izvor: `... nadzor_reklame --url <adresa popisa>`.

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
