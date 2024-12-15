import json
import logging

import requests
from django.http.response import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pyfcm import FCMNotification

from heltour import settings
from heltour.tournament.models import FcmSub

logger = logging.getLogger(__name__)


def _get_fcm_key():
    with open(settings.FCM_API_KEY_FILE_PATH) as fin:
        return fin.read().strip()


def _get_push_service():
    return FCMNotification(api_key=_get_fcm_key())


available_topics = [
    ("[Team]", "team_a"),
    ("[Lonewolf]", "lonewolf_a"),
    ("[Ladder]", "ladder_a"),
    ("[Blitz]", "blitz_a"),
    ("[Ledger]", "ledger_a"),
]


@csrf_exempt
@require_POST
def slack_event(request):
    args = json.loads(request.body.decode("utf-8"))
    token = args.get("token")
    if token != settings.SLACK_APP_TOKEN:
        # Discard request - couldn't verify it was from Slack
        return HttpResponse("Bad verification token", status=400)

    request_type = args.get("type")

    if request_type == "url_verification":
        return HttpResponse(args.get("challenge"))

    if request_type == "event_callback":
        event = args.get("event")
        event_type = event.get("type")
        if event_type == "message":
            channel = event.get("channel")
            users = args.get("authed_users")
            sender = event.get("user")
            ts = event.get("event_ts")
            # Apart from announcements, discard text for privacy
            if channel == settings.SLACK_ANNOUNCE_CHANNEL:
                text = event.get("text", "")
            else:
                text = ""
            process_slack_message(users, channel, sender, text, ts)

    return HttpResponse("ok")


def process_slack_message(users, channel, sender, text, ts):
    logger.warning(
        "Received slack message: %s %s %s %s %s"
        % (",".join(users), channel, sender, text, ts)
    )
    if channel == settings.SLACK_ANNOUNCE_CHANNEL:
        topics = [
            name for match, name in available_topics if match.lower() in text.lower()
        ]
        if len(topics) > 0:
            topic_condition = "'" + "' in topics || '".join(topics) + "' in topics"
            _get_push_service().notify_topic_subscribers(condition=topic_condition)
    elif channel[0] in ("D", "G"):
        # IM or MPIM
        other_users = [u for u in users if u != sender]
        reg_ids = [
            sub.reg_id for sub in FcmSub.objects.filter(slack_user_id__in=other_users)
        ]
        if len(reg_ids) > 0:
            _get_push_service().notify_multiple_devices(registration_ids=reg_ids)


@csrf_exempt
@require_POST
def fcm_register(request):
    args = json.loads(request.body.decode("utf-8"))
    slack_token = args.get("slack_token")
    reg_id = args.get("reg_id")

    url = "https://slack.com/api/auth.test"
    r = requests.get(url, params={"token": slack_token})
    slack_user_id = r.json().get("user_id")
    if not slack_user_id:
        logger.warning("Couldn't validate slack token for FCM registration")
        return HttpResponse("Could not validate slack token", status=400)

    FcmSub.objects.update_or_create(
        reg_id=reg_id, defaults={"slack_user_id": slack_user_id}
    )
    logger.warning("FCM registration complete for %s %s" % (slack_user_id, reg_id))

    return HttpResponse("ok")


@csrf_exempt
@require_POST
def fcm_unregister(request):
    args = json.loads(request.body.decode("utf-8"))
    reg_id = args.get("reg_id")

    FcmSub.objects.filter(reg_id=reg_id).delete()
    logger.warning("FCM unregistration complete for %s" % reg_id)

    return HttpResponse("ok")
