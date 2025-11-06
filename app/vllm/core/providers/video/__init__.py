# video providers
from .wav2lip_provider import Wav2LipProvider
from .fal_infinitalk_provider import FalInfinitalkProvider
from .fal_veo3_provider import FalVeo3Provider
from .sadtalker_provider import SadTalkerProvider
from .did_provider import DIDProvider
from .runpod_infinitetalk_provider import RunpodInfiniteTalkProvider


VIDEO_PROVIDERS = {
    "wav2lip": Wav2LipProvider,
    "fal_infinitalk": FalInfinitalkProvider,
    "fal_veo3": FalVeo3Provider,
    "sadtalker": SadTalkerProvider,
    "did": DIDProvider,
    "runpod_infinitetalk": RunpodInfiniteTalkProvider
}