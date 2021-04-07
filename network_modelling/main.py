import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import SubsetRandomSampler
import torchvision
import torchvision.transforms as transforms

import os
import numpy as np

from models.LSTM import LSTM
from train import train
from test import test
from dataset import FOIKineticPoseDataset
from helpers.paths import EXTR_PATH
from sequence_transforms import FilterJoints, ChangePoseOrigin, ToTensor, NormalisePoses, AddNoise


def create_samplers(dataset_len, train_split=.8, validation_split=.2, val_from_train=True, shuffle=True):
    """

    Influenced by: https://stackoverflow.com/a/50544887

    This is not (as of yet) stratified sampling,
    read more about it here: https://stackoverflow.com/a/52284619

    :param dataset_len:
    :param train_split:
    :param validation_split:
    :param val_from_train:
    :param shuffle:
    :return:
    """

    indices = list(range(dataset_len))

    if shuffle:
        random_seed = 42
        np.random.seed(random_seed)
        np.random.shuffle(indices)

    if val_from_train:
        train_test_split = int(np.floor(train_split * dataset_len))
        temp_indices, test_indices = indices[:train_test_split], indices[train_test_split:]

        train_val_split = int(np.floor((1 - validation_split) * train_test_split))
        train_indices, val_indices = temp_indices[:train_val_split], temp_indices[train_val_split:]

    else:
        test_split = 1 - (train_split + validation_split)

        # Check that there is a somewhat reasonable split left for testing
        assert test_split >= 0.1

        first_split = int(np.floor(train_split * dataset_len))
        second_split = int(np.floor((train_split + test_split) * dataset_len))
        train_indices, test_indices, val_indices = indices[:first_split], indices[first_split:second_split], indices[second_split:]

    return SubsetRandomSampler(train_indices), SubsetRandomSampler(test_indices), SubsetRandomSampler(val_indices)


def check_dataset_item(item):
    seq = item["sequence"]
    print(seq.shape)
    dim = ""

    if isinstance(seq, np.ndarray):
        dim = seq.shape
    elif isinstance(seq, list):
        dim = len(seq)
    elif isinstance(seq, torch.Tensor):
        dim = seq.size()

    print("Dataset instance with index {} and key '{}'\n\ttype: {}, \n\tDimensions: {}"
          .format(item["seq_idx"], item["key"], type(seq), dim))


if __name__ == "__main__":
    # Hyper parameters:
    hidden_size = 128
    num_classes = 10
    start_epoch = 1
    num_epochs = 2
    batch_size = 2
    learning_rate = 0.001

    input_size = 28
    sequence_len = 100
    num_layers = 2

    # Loss function
    margin = 0.2

    # Other params
    json_path = EXTR_PATH + "final_data_info.json"
    root_dir = EXTR_PATH + "final/"

    use_cuda = torch.cuda.is_available()

    # Add checkpoint dir if it doesn't exist
    if not os.path.isdir('./checkpoints'):
        os.mkdir('./checkpoints')

    # Add saved_models dir if it doesn't exist
    if not os.path.isdir('./models/saved_models'):
        os.mkdir('./models/saved_models')

    # Limiter #################################################################
    #   Used to specify which sequences to extract from the dataset.
    #   Values can either be 'None' or a list of indices.
    #
    #   If 'None', don't limit that parameter, e.g.
    #       "subjects": None, "sessions": None, "views": None
    #        will get all sequences, from s0_s0_v0 to s9_s0_v4
    #
    #   If indices, get the corresponding sequences, e.g.
    #       "subjects": [0], "sessions": [0,1], "views": [0,1,2]
    #       will get s0_s0_v0, s0_s0_v1, s0_s0_v2, s0_s1_v0, s0_s1_v1, s0_s1_v2
    #
    ###########################################################################
    data_limiter = {
        "subjects": None,
        "sessions": None,
        "views": None,
    }

    # Transforms
    composed = transforms.Compose([
        ChangePoseOrigin(),
        FilterJoints(),
        NormalisePoses(),
        ToTensor()
    ])

    dataset = FOIKineticPoseDataset(json_path, root_dir, sequence_len, data_limiter, transform=composed)

    train_sampler, test_sampler, val_sampler = create_samplers(len(dataset), train_split=0.6, validation_split=0.1)

    train_loader = DataLoader(dataset, batch_size, sampler=train_sampler, num_workers=2)
    test_loader = DataLoader(dataset, batch_size, sampler=test_sampler, num_workers=2)
    val_loader = DataLoader(dataset, batch_size, sampler=val_sampler, num_workers=2)

    #check_dataset_item(dataset[3])

    model = LSTM(input_size, hidden_size, num_layers, num_classes)

    if use_cuda:
        model.cuda()
        cudnn.benchmark = True
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')

    triplet_loss = nn.TripletMarginLoss(margin)

    optimizer = torch.optim.Adam(model.parameters())

    model, loss_log, acc_log = train(model, train_loader, optimizer, triplet_loss, device, start_epoch, num_epochs)

