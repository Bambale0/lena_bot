"""Budgeted real KIE Kling 4 smoke. No retries of paid POSTs.

Requires explicit --execute and --budget-credits; outputs contain no credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import kieai_client
from api.kie_webhook import extract_result_urls
from api.kling4_contract import KEYFRAME_MODEL, REFERENCE_MODEL, Kling4Input, build_kling4_payload


def fixture_files(directory, portrait=None):
    from PIL import Image, ImageDraw

    directory.mkdir(parents=True, exist_ok=True)
    for index, color in enumerate(["#d1495b", "#edae49"]):
        canvas = Image.new("RGB", (1280, 720), "#e7ecef")
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((440 + index * 40, 170, 800 + index * 40, 530), fill=color)
        if portrait:
            canvas = Image.open(portrait).convert("RGB").resize((720, 720))
        canvas.save(directory / f"frame{index}.png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(directory / "frame0.png"),
            "-t",
            "3",
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            str(directory / "video.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "espeak-ng",
            "-s",
            "110",
            "-w",
            str(directory / "voice.wav"),
            "Hello, welcome to our creative studio. Let us tell a bright story together.",
        ],
        check=True,
    )


async def run(args):
    directory = Path(args.output)
    fixture_files(directory, args.portrait)
    urls = {}
    for name, mime in [
        ("frame0.png", "image/png"),
        ("frame1.png", "image/png"),
        ("video.mp4", "video/mp4"),
        ("voice.wav", "audio/wav"),
    ]:
        urls[name] = await kieai_client.upload_file_stream(
            (directory / name).read_bytes(),
            filename=name,
            content_type=mime,
            upload_path="kling4-smoke",
        )
    cases = []
    for model in [KEYFRAME_MODEL, REFERENCE_MODEL]:
        for res in ["720p", "1080p"]:
            fields = (
                {"first_frame_url": urls["frame0.png"], "last_frame_url": urls["frame1.png"]}
                if model == KEYFRAME_MODEL
                else {"image_urls": [urls["frame0.png"]]}
            )
            cases.append(
                (
                    f"{model}:{res}",
                    model,
                    Kling4Input(duration=3, resolution=res, **fields),
                    3 * (28.5 if res == "720p" else 42.5),
                    "A colorful ball gently moves across a clean studio. Smooth cinematic movement.",
                )
            )
    for res, rate in [("720p", 17), ("1080p", 25.5)]:
        cases.append(
            (
                f"reference-video:{res}",
                REFERENCE_MODEL,
                Kling4Input(duration=3, resolution=res, video_urls=[urls["video.mp4"]]),
                6 * rate,
                "@video_1 Continue the ball movement with a gentle camera pan.",
            )
        )
    cases.append(
        (
            "video-element-only",
            REFERENCE_MODEL,
            Kling4Input(duration=3, elements=[{"name": "Hero", "video_url": urls["video.mp4"]}]),
            6 * 17,
            "@Hero moves gently in a bright studio.",
        )
    )
    cases.append(
        (
            "image-element-bound-and-standalone-voice",
            REFERENCE_MODEL,
            Kling4Input(
                duration=3,
                elements=[
                    {
                        "name": "Hero",
                        "image_urls": [urls["frame0.png"], urls["frame1.png"]],
                        "voice_url": urls["voice.wav"],
                        "tag": "character",
                    }
                ],
                voices=[{"name": "Narrator", "audio_url": urls["voice.wav"]}],
            ),
            85.5,
            "@Hero rolls forward. @Narrator says hello and welcomes the viewer.",
        )
    )
    if "mixed-video-element" in args.case:
        cases.append(
            (
                "mixed-video-element",
                REFERENCE_MODEL,
                Kling4Input(
                    duration=3,
                    video_urls=[urls["video.mp4"]],
                    elements=[{"name": "Hero", "video_url": urls["video.mp4"]}],
                ),
                153,
                "@Hero waves. Use @video_1 as a motion reference.",
            )
        )
    if "fractional-video" in args.case:
        fractional = directory / "fractional.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-stream_loop",
                "-1",
                "-i",
                str(directory / "video.mp4"),
                "-t",
                "3.1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(fractional),
            ],
            check=True,
        )
        fractional_url = await kieai_client.upload_file_stream(
            fractional.read_bytes(),
            filename="fractional.mp4",
            content_type="video/mp4",
            upload_path="kling4-smoke",
        )
        cases.append(
            (
                "fractional-video",
                REFERENCE_MODEL,
                Kling4Input(duration=3, video_urls=[fractional_url]),
                119,
                "@video_1 Continue the motion gently.",
            )
        )
    if args.case:
        cases = [case for case in cases if case[0] in args.case]
    if sum(case[3] for case in cases) + args.prior_spend_credits > args.budget_credits:
        raise ValueError("Worst-case forecast exceeds budget; no paid request made")
    reports = []

    def save():
        (directory / "report.json").write_text(json.dumps(reports, indent=2))

    for label, model, data, forecast, prompt in cases:
        payload = build_kling4_payload(model, prompt, data)
        report = {
            "case": label,
            "payload_hash": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            "forecast_credits_max": forecast,
            "started_at": time.time(),
        }
        reports.append(report)
        save()
        try:
            response = await kieai_client.create_task(payload)
            report["task_id"] = response["data"]["taskId"]
            report["state"] = "submitted"
        except Exception as exc:
            report["state"] = (
                "submission_unknown"
                if isinstance(exc, kieai_client.KieSubmissionOutcomeUnknown)
                else "rejected"
            )
            report["error_type"] = type(exc).__name__
            save()
            print(json.dumps(report), flush=True)
            # Unknown acceptance stops all further paid smoke calls.
            if report["state"] == "submission_unknown":
                return
        save()
    deadline = time.monotonic() + 2400
    while time.monotonic() < deadline:
        active = False
        for report in reports:
            if report.get("state") not in {"submitted", "waiting", "queuing", "generating"}:
                continue
            active = True
            try:
                response = await kieai_client.get_task_status(report["task_id"])
                data = response.get("data") or {}
                report["state"] = data.get("state") or "submitted"
                report["credits_consumed"] = data.get("creditsConsumed")
                report["elapsed_seconds"] = round(time.time() - report["started_at"], 2)
                if report["state"] in {"success", "fail"}:
                    report["result_urls"] = extract_result_urls(response)
                    report["fail_code"] = data.get("failCode")
                    report["fail_message"] = data.get("failMsg")
                    print(json.dumps(report), flush=True)
            except Exception as exc:
                report["last_get_error"] = type(exc).__name__
            save()
        if not active:
            break
        await asyncio.sleep(20)
    await kieai_client.close_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--portrait")
    parser.add_argument("--prior-spend-credits", type=float, default=0)
    parser.add_argument("--budget-credits", type=float, default=0)
    parser.add_argument("--output", default="/tmp/apix-kling4-live")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Paid calls require --execute and --budget-credits")
    asyncio.run(run(args))
