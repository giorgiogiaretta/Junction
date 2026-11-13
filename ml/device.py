"""Pick the best torch device on any teammate machine: CUDA (Giorgio's MSI, 12 GB) > MPS (Tommaso's MacBook M2) > CPU."""
import torch

def pick_device(prefer=None):
    if prefer: return torch.device(prefer)
    if torch.cuda.is_available(): return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available(): return torch.device("mps")
    return torch.device("cpu")

if __name__ == "__main__":
    d = pick_device(); print("device:", d, "| torch", torch.__version__)
    if d.type == "cuda": print(torch.cuda.get_device_name(0), round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1), "GB")
