# LINE LIFF and Rich Menu setup

Use LINE Official Account Manager for the default Rich Menu. A menu created in
Official Account Manager cannot be edited through the Messaging API, and the
reverse is also true, so keep one owner and remove the API setup script after
cutover.

## 1. Register the LIFF app

1. Open LINE Developers Console.
2. Select the provider and LINE Login channel linked to this product.
3. Add a LIFF app with the production endpoint `https://<domain>/webapp`.
4. Use a tall or full view and enable the `openid` and `profile` scopes.
5. Save the LIFF ID as `LIFF_ID`; save the LINE Login channel ID as
   `LINE_LOGIN_CHANNEL_ID`.
6. Configure the backend to verify the ID token and use its `sub` as the user
   identity.

The Rich Menu LIFF links should use:

```text
https://liff.line.me/<LIFF_ID>?tab=today
https://liff.line.me/<LIFF_ID>?tab=history
https://liff.line.me/<LIFF_ID>?tab=programs
https://liff.line.me/<LIFF_ID>?tab=profile
```

## 2. Create the Rich Menu image

In LINE Official Account Manager, select the account, open **Rich menus** and
create an always-visible menu using a 3×2 template. Upload one PNG or JPEG that
matches the template dimensions.

Suggested labels:

```text
Camera | Today | เวท
History | Profile | Help
```

Keep labels large and high contrast; the bottom menu is primarily used on a
phone. Rich menus are not displayed in LINE for PC.

## 3. Configure the six actions

| Area | Action |
| --- | --- |
| Camera | Open `https://line.me/R/nv/camera/` |
| Today | Open `https://liff.line.me/<LIFF_ID>?tab=today` |
| เวท | Send message `เวท` |
| History | Open `https://liff.line.me/<LIFF_ID>?tab=history` |
| Profile | Open `https://liff.line.me/<LIFF_ID>?tab=profile` |
| Help | Send message `วิธีใช้` |

Set the chat-bar label to a short value such as `เมนู LINE Cal`, publish it as
the default Rich Menu and test all six areas from LINE on a phone.

## 4. Remove the competing setup path

After the Official Account Manager menu is active:

1. Remove `scripts/setup_rich_menu.py` from the product.
2. Remove obsolete API-created Rich Menus if they are still set as default.
3. Keep the action mapping in this document as the source of truth.

Official references:

- [Rich menus overview](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/)
- [LIFF server API](https://developers.line.biz/en/reference/liff-server/)
