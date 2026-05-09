# DeepSeek API Key Guide

This guide explains how to create a DeepSeek API Key for AiNiee-Next. It is written without screenshots so the steps are clear even if the website layout changes slightly.

DeepSeek is used in these guides because it is inexpensive, practical, and usually good enough for a first translation workflow. It is not the only option; it is simply a good example platform for new users.

DeepSeek Open Platform:

```text
https://platform.deepseek.com/
```

Important: an API Key is like a paid access password. Keep it private. If someone else gets your key, they can use your DeepSeek balance.

## 1. Open the DeepSeek Open Platform

Go to:

```text
https://platform.deepseek.com/
```

Sign in or register with the method shown on the page.

For the overseas site, DeepSeek commonly uses email registration or email login. Enter your email address, complete the verification step, and follow the platform instructions to create or access your account.

If the page offers other login methods in your region, follow the current DeepSeek website instructions.

## 2. Complete Real-Name Verification

After logging in, open the personal account or profile page.

Look for the real-name verification status. If the account is not verified, follow the platform instructions to complete verification.

DeepSeek API is a paid usage-based service. In many cases, API key creation or API usage may require account verification. Follow the current DeepSeek website instructions if the process changes.

## 3. Add Balance

Open the recharge or top-up page.

For a first test, a small amount is enough. Usually, `10 RMB` can last a long time for light usage or testing. If you translate large projects later, recharge based on actual usage.

Notes:

- This balance is for API usage.
- It is separate from whether the DeepSeek web chat or app has free usage.
- API calls made by tools such as AiNiee-Next consume API balance.

## 4. Open the API Keys Page

In the DeepSeek Open Platform sidebar or account menu, find:

```text
API keys
```

This page lists your existing keys. Existing keys are usually shown only in masked form, such as:

```text
sk-xxxx********xxxx
```

You normally cannot view the full key again after closing the creation window.

## 5. Create a New API Key

Click the button for creating a new API key.

The platform may ask for a key name. This name is only for your own organization. Use something easy to recognize, for example:

```text
AiNiee
AiNiee-Next
Novel-Translation
Manga-Translation
```

The name does not affect API behavior.

After entering a name, confirm creation.

## 6. Copy and Save the API Key

After creation, DeepSeek will show the full API Key once.

Immediately copy it and save it somewhere secure, such as:

- a password manager,
- an encrypted note,
- or another private place that only you can access.

Do not rely on the DeepSeek page to show the full key again later. If you close the window without saving the key, you may need to delete that key and create a new one.

## 7. Security Rules

Follow these rules:

- Do not send your API Key to other people.
- Do not post it in chat groups, forums, issues, screenshots, or support tickets.
- Do not commit it to a public repository.
- Do not paste it into public documents.
- If you suspect a key has leaked, delete it immediately and create a new one.
- If your balance decreases unexpectedly, check billing records and disable suspicious keys.

This matters because leaked keys can spend your money.

## 8. Use the Key in AiNiee-Next

Return to AiNiee-Next and open the API configuration menu.

Choose DeepSeek and fill in:

- **API Key**: paste the key copied from the DeepSeek platform.
- **Model**: start with the preset model, or choose another valid DeepSeek model.
- **API URL**: normally use the preset value.

Common DeepSeek API URL:

```text
https://api.deepseek.com/v1
```

After saving, run API verification before starting a real translation.

If verification fails, check:

- whether the key was pasted correctly,
- whether the account has balance,
- whether the model name is valid,
- whether the API URL is correct,
- whether OpenAI SDK request mode should be enabled for DeepSeek.

After verification succeeds, continue with the quick start guide:

[AiNiee-Next Text Quick Start Guide](README_QUICK_START_EN.md)
