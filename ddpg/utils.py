import numpy as np
import torch

USE_CUDA = torch.cuda.is_available()
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


class RunningMeanStd(object):
    def __init__(self, epsilon=1e-2):
        self._sum = 0.0
        self._sumsq = epsilon
        self._count = epsilon

        self.mean = self._sum / self._count
        self.std = np.sqrt(np.max([self._sumsq / self._count - np.square(self.mean), 1e-2]))
    
    def update(self, x):
        x = x.astype('float64')
        self._sum += x.sum(axis=0)
        self._sumsq += np.square(x).sum(axis=0)
        self._count += len(x)

        self.mean = self._sum / self._count
        self.std = np.sqrt(np.clip(self._sumsq / self._count - np.square(self.mean), 1e-2, np.inf))


def soft_update(target, source, tau):
    for target_param, param in zip(target.parameters(), source.parameters()):
        target_param.data.copy_(target_param.data * (1.0 - tau) + param.data * tau)


def hard_update(target, source):
    for target_param, param in zip(target.parameters(), source.parameters()):
        target_param.data.copy_(param.data)


def to_numpy(var):
    return var.cpu().data.numpy() if USE_CUDA is True else var.data.numpy()


def to_tensor(ndarray):
    tensor = torch.from_numpy(ndarray).float()
    return tensor.to(device) if USE_CUDA is True else tensor
