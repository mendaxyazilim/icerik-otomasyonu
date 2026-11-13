# İçerik Otomasyonu

Her gün bir Türkçe kısa video (Instagram Reels + YouTube Shorts) üreten ve onayınla Buffer üzerinden yayınlayan sistem.

**Akış:** konu (`content/topics.txt`) → Gemini senaryo + sahne planı → Gemini TTS seslendirme → avatarlı animasyon videosu →
`media` dalına (herkese açık link) → onay için GitHub Issue → `yayınla` yorumu → Buffer → Instagram + YouTube.

## Kurulum (bir kez)

1. **Secrets** (Settings → Secrets and variables → Actions → *New repository secret*):
   - `GEMINI_API_KEY`: aistudio.google.com/apikey
   - `BUFFER_API_KEY`: publish.buffer.com/settings/api
2. Buffer'da Instagram (işletme/creator hesabı) ve YouTube kanalını bağla.
3. Actions → **Buffer kanallarını kontrol et** → *Run workflow*: kanallar listelenmeli.
4. Actions → **Günlük video** → *Run workflow*: ilk videoyu üretir ve onay için bir Issue açar.

## Günlük kullanım

- Her gün 16:17'de (TR) video üretilir, **Issues** altında "Onay: ..." başlıklı bir konu açılır (GitHub mobil uygulamasından bildirim gelir).
- Videoyu izle; beğendiysen konuya **yayınla** yaz, beğenmediysen **iptal** yaz.
- Onaysız yayın istersen: Settings → Secrets and variables → Actions → **Variables** → `REQUIRE_APPROVAL` = `false`.

## Ayarlar

- `config.yaml`: ses (`voice.name`), modeller, kapanış çağrısı, affiliate linkleri, yayın kanalları.
- `content/topics.txt`: konu sırası. Biterse sistem yeni konu üretir. Belirli bir konuyla üretmek için *Run workflow* ekranındaki "Konu" alanını kullan.
- Sahne şablonları: `studio/scenes.py`. Avatar: `assets/avatar.png`.

## Yerel test (API'siz)

```bash
pip install -r requirements.txt   # + ffmpeg
python -m studio.main render --storyboard ornek.json --audio ses.wav --out out
```

Fontlar: Inter ve Lora (SIL Open Font License).
