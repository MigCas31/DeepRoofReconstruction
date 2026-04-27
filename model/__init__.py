__all__ = [
    "LossWeights",
    "RoofRefineNet",
    "composite_loss",
    "load_example",
    "load_tier_payload",
    "tensorize_example",
]


def __getattr__(name: str):
    if name in {"load_example", "load_tier_payload", "tensorize_example"}:
        from model.data import load_example, load_tier_payload, tensorize_example

        return {
            "load_example": load_example,
            "load_tier_payload": load_tier_payload,
            "tensorize_example": tensorize_example,
        }[name]
    if name in {"LossWeights", "composite_loss"}:
        from model.losses import LossWeights, composite_loss

        return {"LossWeights": LossWeights, "composite_loss": composite_loss}[name]
    if name == "RoofRefineNet":
        from model.roof_refine_net import RoofRefineNet

        return RoofRefineNet
    raise AttributeError(f"module 'model' has no attribute {name!r}")

