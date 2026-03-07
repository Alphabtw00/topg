#!/bin/bash
# ============================================================
#  PURGE SENSITIVE FILES FROM GIT HISTORY
#  Run this from the ROOT of your local repo
#  Make sure you have a backup or the repo cloned fresh first
# ============================================================

set -e

echo "==> Checking git-filter-repo is installed..."
if ! command -v git-filter-repo &>/dev/null; then
  echo "Installing git-filter-repo..."
  pip install git-filter-repo --break-system-packages
fi

echo ""
echo "==> Starting history purge for all sensitive files..."
echo ""

git filter-repo --force \
  --path who_added_bot_test.py \
  --path social_tracker_forward.py \
  --path second.py \
  --path check_server_roles_test.py \
  --path server_bot_list_test.py \
  --path preview.py \
  --path preview.png \
  --path highest.py \
  --path helius.py \
  --path github_response_3.json \
  --path github_response_2.json \
  --path github_response_1.json \
  --path generate_files.py \
  --path generate_document.py \
  --path filtered_transactions.json \
  --path check_members_in_server_with_role.py \
  --path react_with_emoji.py \
  --path embed.py \
  --path .env \
  --path data/ \
  --path delete_member_messages.py \
  --path copy_server_emoji.py \
  --path get_audit_logs.py \
  --path print_messages_in_channel.py \
  --invert-paths

echo ""
echo "==> Local history cleaned. Re-adding remote origin..."

# Replace with your actual remote URL if needed
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")

if [ -z "$REMOTE_URL" ]; then
  echo "WARNING: No remote 'origin' found. Add it manually with:"
  echo "  git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
else
  # git filter-repo removes the remote as a safety measure, re-add it
  git remote add origin "$REMOTE_URL"
  echo "Remote re-added: $REMOTE_URL"
fi

echo ""
echo "==> Pushing cleaned history to GitHub (force push)..."
echo "    This will overwrite remote history permanently."
echo ""

read -p "Are you sure you want to force push? (yes/no): " CONFIRM
if [ "$CONFIRM" = "yes" ]; then
  git push origin --force --all
  git push origin --force --tags
  echo ""
  echo "✅ Done! All sensitive files removed from history."
  echo ""
  echo "NEXT STEPS:"
  echo "  1. Revoke ALL secrets/tokens/webhooks that were in those files"
  echo "  2. If repo is/was public, treat ALL secrets as compromised"
  echo "  3. Anyone who cloned the repo should re-clone fresh"
  echo "  4. Contact GitHub support to purge their cache if repo was public:"
  echo "     https://support.github.com/contact"
  echo "  5. Add .env and sensitive files to .gitignore going forward"
else
  echo "Push cancelled. Your local history is clean but remote is unchanged."
  echo "Run this when ready: git push origin --force --all"
fi