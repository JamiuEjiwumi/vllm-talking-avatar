# video providers
from .wav2lip_provider import Wav2LipProvider
# from .infinitetalk_provider import InfiniteTalkProvider
# from .veo_provider import VeoProvider
from .fal_infinitalk_provider import FalInfinitalkProvider
from .fal_veo3_provider import FalVeo3Provider


VIDEO_PROVIDERS = {
    "wav2lip": Wav2LipProvider,
    # "infinitetalk": InfiniteTalkProvider,
    # "veo3": VeoProvider,
    "fal_infinitalk": FalInfinitalkProvider,
    "fal_veo3": FalVeo3Provider,
}