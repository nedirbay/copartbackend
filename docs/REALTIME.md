# Real-time täzelenmeler (WebSocket)

Bir ulanyjy maglumaty üýtgedende (awtoulag, status, çykdajy, resminama, tabşyryş, sözlük, işgär),
beýleki ulanyjylaryň web we mobil programmalarynda sahypa täzelenmän derrew görünýär.

## Nähili işleýär

```
Admin (web)  --POST /api/vehicles/.../assign/-->  Django (REST)
                                                     |  model signal -> on_commit
                                                     v
                                              Redis (channel layer)
                                                     |
             +---------------------------------------+-------------------------+
             v                                       v                         v
   Admin (web, beýleki tab)              Işgär (mobil)               Işgär (web)
   {"type":"vehicle.changed","vin":...}  -> GET /api/vehicles/<vin>/ (täzeden okaýar)
```

* Wakalar **ýeňil signallardyr** — içinde maglumat ýok. Müşderi wakany alanda degişli REST
  endpointinden täzeden okaýar. Şonuň üçin ähli hukuk barlaglary diňe REST-de galýar.
* Awtoulag wakasy diňe ony görmäge hukugy bolanlara gidýär: Adminler, jogapkär işgär,
  kabul etmäge garaşýan işgär we (awtoulag başga birine geçen bolsa) öňki jogapkär.
* Wakalar tranzaksiýa üstünlikli tamamlanandan soň ugradylýar; bir HTTP soragynyň içindäki
  birmeňzeş wakalar bir gezek ugradylýar.
* Redis işlemese REST işläp dur, diňe real-time wakalar gitmeýär (log-da duýduryş).

Kod: `apps/realtime/` (signals, consumer, JWT middleware), `config/asgi.py`.

## Protokol

Birikmek: `wss://<host>/ws/?token=<JWT access token>`

| Serwer -> müşderi | Kime | Müşderi näme etmeli |
|---|---|---|
| `{"type":"hello","user_id":5}` | birikende | (gaýtadan birikende — ähli sahypalary täzelemeli) |
| `{"type":"vehicle.changed","vin":"..."}` | Admin + jogapkär + garaşýan + öňki jogapkär | sanawy / şol awtoulagy täzeden okamak |
| `{"type":"vehicle.deleted","vin":"..."}` | şolar | sanawdan aýyrmak, jikme-jik sahypadan çykmak |
| `{"type":"notifications.changed"}` | bildirişiň eýesi | okalmadyk sanyny / sanawy täzelemek |
| `{"type":"notification.created","id":7,"vehicle":"VIN","kind":"EXPENSE_ADDED","message":"..."}` | bildirişiň eýesi | popup (web) / Android ulgam bildirişini görkezmek |
| `{"type":"dictionary.changed","name":"statuses"}` | hemmeler | sözlügi täzeden okamak (`statuses`, `locations`, `makes`, `models`, `currencies`, `expense_types`) |
| `{"type":"employees.changed"}` | Adminler | işgärler sanawyny täzelemek |
| `{"type":"session.revoked"}` + ýapylyş `4003` | işjeňsizleşdirilen ulanyjy | ulgamdan çykarmak, gaýtadan birikmezlik |

Müşderi -> serwer: `{"type":"ping"}` -> `{"type":"pong"}` (nginx / proksi boş birikmäni ýapmaz ýaly, ~25 sekuntda bir).

Ýapylyş kodlary: `4001` — token ýok / möhleti geçen (tokeni täzeläp gaýtadan birikmeli),
`4003` — sessiýa ýatyryldy.

## Bildirişler

Bildiriş (`Notification`) şu ýagdaýlarda döredilýär we `notification.created` bilen derrew görkezilýär:

| Waka | Kime |
|---|---|
| Täze awtoulag hasaba alyndy | jogapkär işgär + beýleki Adminler |
| Berkidildi / mejbury geçirildi / dolandyryş yzyna alyndy | degişli işgär(ler) |
| Status üýtgedi | Admin etse — jogapkär, işgär etse — Adminler |
| Tabşyryş haýyşy / kabul / ret / ýatyrma | degişli işgärler (+ Adminler kabul edilende) |
| Täze çykdajy, täze resminama | Admin goşsa — jogapkär, işgär goşsa — Adminler |

Hereketi edeniň özüne bildiriş gitmeýär. Telegram sazlanan bolsa oňa hem ugradylýar.

Mobil: programma açyk wagty bildiriş WebSocket arkaly, ýapyk wagty FCM arkaly gelýär.
Iki ýoldan hem gelse ID birmeňzeş — telefon bir bildiriş görkezýär.

### FCM (push) sazlamak

1. Firebase Console -> ⚙️ Project settings -> **Service accounts** -> *Generate new private key*.
2. JSON faýly serwere goýuň (git-e däl!), meselem `/etc/copart/firebase-service-account.json`,
   we diňe backend ulanyjysy okap biler ýaly: `chmod 600`.
3. `.env`: `FIREBASE_CREDENTIALS_FILE=/etc/copart/firebase-service-account.json`
4. `pip install -r requirements.txt && python manage.py migrate`, serweri täzeden açyň.
5. Serwer `fcm.googleapis.com` we `oauth2.googleapis.com` salgylaryna çykyp bilmeli.

Mobil programma girişden soň tokenini `POST /api/notifications/devices/ {"token": "..."}` bilen
hasaba alýar. Ýaramsyz tokenler (programma pozulan) ugradylanda awtomatik arassalanýar.

## Lokal işletmek

```bash
pip install -r requirements.txt
python manage.py runserver        # daphne INSTALLED_APPS-da — runserver WebSocket-i hem goldaýar
```

`REDIS_URL` boş bolsa kanal gatlagy ýadyda işleýär (diňe bir prosess bilen ýeterlik).
Vue dev serweri (`vite`) `/ws` ýoluny backend-e proksi edýär.

## Production

1. **Redis** gurnaň we `.env`-e goşuň (birnäçe prosess/worker bolsa hökmany):
   ```
   REDIS_URL=redis://127.0.0.1:6379/0
   ```
2. Django-ny **ASGI** serwer bilen işlediň (gunicorn/WSGI WebSocket-i goldamaýar):
   ```bash
   daphne -b 127.0.0.1 -p 8000 config.asgi:application
   ```
   Ýa-da HTTP üçin gunicorn galdyryp, diňe `/ws/` üçin aýratyn daphne işledip bolýar —
   bu ýagdaýda hem `REDIS_URL` hökmany (gunicorn wakalary Redis arkaly daphne-ä geçirýär).
3. **nginx** — `/ws/` üçin Upgrade sözbaşylary:
   ```nginx
   location /ws/ {
       proxy_pass http://127.0.0.1:8000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header Host $host;
       proxy_read_timeout 120s;
   }
   ```

## Testler

```bash
pytest tests/test_realtime.py
```
