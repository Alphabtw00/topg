# TOPG Bot – Privacy Policy

_Last updated: October 24, 2026_

This policy explains what data the TOPG Discord bot ("TOPG", "the bot") collects, why, and how it is handled. By adding TOPG to a server or using its commands, you agree to this policy.

## What we collect

**Message content (not stored)**
- **Channel forwarding:** in channels that server admins have configured for forwarding, the bot reads each new message's text, embeds and attachments and re-posts them to the configured output channel. This happens in memory only. The content is not saved by the bot.
- **Word counter:** the bot checks message text for one specific tracked word. Only the resulting number is saved (see below). The message text is discarded immediately.

**Data we store**
- **Word counts:** your Discord user ID, the server ID, a count, and the time it was last updated.
- **Server and channel settings:** server IDs, channel IDs and on/off settings that admins choose (for example forwarding or tracker channels).
- **Token call records:** if a server uses token call tracking, the bot may store the Discord user ID, username, server ID, channel ID, message ID, token address and price at the time of the call.
- **Analysis cache:** results of `/github-checker` lookups on public GitHub repositories, so repeat lookups are faster. No user data is stored with these.

**Server members (not stored)**
- When moderation is enabled for a server, the bot checks the usernames and nicknames of members who join or change their name against blocked patterns, to remove scam or impersonator accounts. These names are checked in memory and are not saved.

**Logs**
- The bot keeps technical log files on its hosting server for troubleshooting. These can include user IDs, usernames, server IDs and channel IDs (for example when a command is used or an error happens). They never include message content. Logs are deleted after at most 90 days.

## What we don't do
- We do not sell, rent or share your data with anyone.
- We do not use your data for advertising or for training AI models.
- We do not store message content.

## Where data is kept
Stored data is kept in a private, password-protected MySQL database with encrypted (SSL) connections. Only the bot's developer can access it.

## Third-party services
To answer commands, the bot sends the inputs you give it (such as a token address, a GitHub repository link or a website link) to public APIs, including DexScreener, GitHub, Kalshi, VirusTotal and Anthropic. Your Discord user data is not sent to these services.

## How long we keep data
- Word counts and token call records are kept while the bot is in the server, or until you ask us to delete them.
- Server and channel settings are kept until an admin changes them or removes the bot.
- Logs are deleted after at most 90 days.

## Your choices
- You can ask us to delete all data linked to your Discord user ID at any time by contacting us (below). We will delete it within 30 days.
- Server admins can remove the bot at any time. To have that server's stored data deleted, contact us.

## Children
TOPG is only for users who meet Discord's minimum age requirement in their country.

## Changes
We may update this policy. The date at the top shows the latest version.

## Contact
Message the developer on Discord: **alphabtw_**
