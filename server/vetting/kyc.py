"""
Identity (NIN + selfie) verification adapters (TUT-07).

The PRD leaves the KYC provider to be chosen after a commercial review
(Prembly / Dojah / VerifyMe / Smile ID). Every provider implements
`verify_nin_selfie(nin, selfie_path, first_name, last_name)` and returns a
KYCResult. The default "manual" provider routes every submission to the
vetting team's manual-review queue, which is also the fallback when a
provider call fails.
"""
from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class KYCResult:
    status: str  # passed | failed | manual_review
    reference: str = ""
    details: dict = field(default_factory=dict)


class ManualProvider:
    name = "manual"

    def verify_nin_selfie(self, nin, selfie_path, first_name, last_name):
        return KYCResult("manual_review", details={"nin_last4": nin[-4:], "reason": "Manual review"})


PROVIDERS = {"manual": ManualProvider}


def get_provider():
    return PROVIDERS.get(settings.KYC_PROVIDER, ManualProvider)()


def verify_identity(nin, selfie_path, first_name, last_name):
    provider = get_provider()
    try:
        return provider.name, provider.verify_nin_selfie(nin, selfie_path, first_name, last_name)
    except Exception as e:  # noqa: BLE001 - fall back to manual review on any provider failure
        return provider.name, KYCResult("manual_review", details={"error": str(e)[:300]})
