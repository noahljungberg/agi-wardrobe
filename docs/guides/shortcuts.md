# iPhone Shortcuts

All three talk to the **private** endpoint
`https://<machine>.<tailnet>.ts.net:8443`. Only your own devices can reach it,
so the Tailscale app on the phone must be connected. Turn on
**Tailscale → VPN On Demand** so it always is.

Every request sends the header `Authorization: Bearer <WARDROBE_DEVICE_TOKEN>`.

## 1. Location when you open ChatGPT (or Claude)

This is what makes "the weather where I am" work without you doing anything.

**Shortcuts → Automation → + → App**

- Choose **ChatGPT** (and **Claude**, if you use it).
- Select **Is Opened** and **Run Immediately**.

Actions:

1. **Get Current Location**
2. **Get Contents of URL**
   - URL: `https://<machine>.<tailnet>.ts.net:8443/location`
   - Method: **POST**
   - Headers: `Authorization` = `Bearer <device token>`
   - Request Body: **JSON**
     - `lat` (Number) = *Current Location → Latitude*
     - `lon` (Number) = *Current Location → Longitude*
     - `name` (Text) = *Current Location → City*
     - `tz` (Text, optional) = *Current Date*, formatted with **Format Date →
       Custom** `VV` (gives e.g. `Europe/Stockholm`)

The server keeps only the latest position. If the phone hasn't reported a
location for 36 hours, the server falls back to `home` in `profile.yaml`. You
can always just say "I'm in San Francisco".

## 2. "Add to wardrobe" from Safari (product pages)

This is the fallback for shops that block the importer. It reads the page in
your own browser and sends what it finds home.

**New Shortcut → name it "Add to wardrobe"**

- Shortcut details: **Show in Share Sheet** on, accepting **Safari web pages**.

Actions:

1. **Run JavaScript on Web Page** with:

   ```js
   var ld = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(function (s) { return s.textContent; });
   var meta = {};
   document.querySelectorAll('meta[property], meta[name]').forEach(function (m) {
     var k = m.getAttribute('property') || m.getAttribute('name');
     if (k && m.content) meta[k] = m.content;
   });
   var images = Array.from(document.images)
     .filter(function (i) { return i.naturalWidth >= 400; })
     .map(function (i) { return i.currentSrc || i.src; })
     .slice(0, 12);
   completion({ url: location.href, title: document.title, jsonld: ld, meta: meta, images: images });
   ```

2. **Get Contents of URL**
   - URL: `https://<machine>.<tailnet>.ts.net:8443/import`
   - Method: **POST**
   - Headers:
     - `Authorization` = `Bearer <device token>`
     - `Content-Type` = `application/json`
   - Request Body: **File** = *JavaScript Result*
3. **Get Dictionary Value** `message` from *Contents of URL*
4. **Show Notification** with *Dictionary Value*

Pick the right colour on the product page before you share it.

## 3. "Add photo to wardrobe" (things with no link)

**New Shortcut → name it "Add photo to wardrobe"**

- Shortcut details: **Show in Share Sheet** on, accepting **Images**.

Actions:

1. **Repeat with Each** item in *Shortcut Input*:
   - **Get Contents of URL**
     - URL: `https://<machine>.<tailnet>.ts.net:8443/inbox`
     - Method: **POST**
     - Headers: `Authorization` = `Bearer <device token>`
     - Request Body: **Form**, field `photo` (File) = *Repeat Item*
2. **Show Notification**: "Sent to wardrobe inbox"

Next time you chat, say "check my wardrobe inbox". The assistant looks at the
photos, proposes names and details, and saves them after you say yes.

A plain background and the whole garment in frame give the best results.
