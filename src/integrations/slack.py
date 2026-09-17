"""Slack client/app setup (built on slack-bolt).

Registers the `/trust`, `/revoke`, and `/trust-status` slash commands and
handles Slack request signature verification (SLACK_SIGNING_SECRET) and
posting responses back to Slack (SLACK_BOT_TOKEN). Channel-restriction
enforcement (only the configured trusted_channel_id) and rule-engine
dispatch are handled by src/triggers/slack.py and src/engine/evaluator.py;
this module is the transport layer.
"""

from __future__ import annotations


def create_slack_app(bot_token: str, signing_secret: str):
    """Construct and return the configured slack_bolt App with slash commands registered."""
    raise NotImplementedError
