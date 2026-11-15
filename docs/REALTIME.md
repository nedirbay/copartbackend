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
| `{"type":"dictionary.changed","name":"statuses"}` | hemmeler | sözlügi täzeden okamak (`statuses`, `locations`, `makes`, `models`, `currencies`, `expense_types`) |
| `{"type":"employees.changed"}` | Adminler | işgärler sanawyny täzelemek |
| `{"type":"session.revoked"}` + ýapylyş `4003` | işjeňsizleşdirilen ulanyjy | ulgamdan çykarmak, gaýtadan birikmezlik |

Müşderi -> serwer: `{"type":"ping"}` -> `{"type":"pong"}` (nginx / proksi boş birikmäni ýapmaz ýaly, ~25 sekuntda bir).

Ýapylyş kodlary: `4001` — token ýok / möhleti geçen (tokeni täzeläp gaýtadan birikmeli),
`4003` — sessiýa ýatyryldy.

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
