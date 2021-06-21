import time
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
from model import SSD300, Loss
from dataset import MasksDataset
from utils import *
from eval import evaluate
import constants
import pickle

# Label map
masks_labels = ('proper', 'not_porper')
label_map = {k: v + 1 for v, k in enumerate(masks_labels)}
label_map['background'] = 0
rev_label_map = {v: k for k, v in label_map.items()}  # Inverse mapping

distinct_colors = ['#e6194b', '#3cb44b', '#FFFFFF']
label_color_map = {k: distinct_colors[i] for i, k in enumerate(label_map.keys())}

# Model parameters
n_classes = len(label_map)  # number of different types of objects
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Learning parameters
batch_size = 24  # batch size
workers = 4  # number of workers for loading data in the DataLoader
print_freq = 200  # print training status every __ batches
min_score = 0.01
topk = 200
lr = 1e-2  # learning rate TODO original 1e-3
# momentum = 0.9  # momentum TODO
weight_decay = 5e-4  # weight decay
# clip if gradients are exploding, which may happen at larger batch sizes (sometimes at 32) -
# you will recognize it by a sorting error in the MuliBox loss calculation
grad_clip = None  # TODO

cudnn.benchmark = True

checkpoint = ''  # '/home/student/checkpoint_nvidia_ssd300_epoch=7.pth.tar'
if checkpoint:
    start_epoch = int(checkpoint.split('=')[-1].split('.')[0])
else:
    start_epoch = 0


def main():
    """
    Training.
    """
    global label_map, epoch, decay_lr_at, checkpoint

    # Initialize model
    model = SSD300().to(device)
    if checkpoint:
        checkpoint = torch.load(checkpoint)
        model.load_state_dict(checkpoint['state_dict'])
    print(f"min_score = {min_score}")
    print(f"top_k = {topk}")
    # Initialize the optimizer, with twice the default learning rate for biases, as in the original Caffe repo
    biases = list()
    not_biases = list()
    for param_name, param in model.named_parameters():
        if param.requires_grad:
            if param_name.endswith('.bias'):
                biases.append(param)
            else:
                not_biases.append(param)
    optimizer = torch.optim.Adam(params=[{'params': biases, 'lr': 2 * lr}, {'params': not_biases}],
                                 lr=lr, weight_decay=weight_decay)  # TODO SGD with momentum=momentum \ Adam

    boxes = create_boxes()
    criterion = Loss(boxes).to(device)

    # Custom dataloaders
    train_dataset = MasksDataset(data_folder=constants.TRAIN_IMG_PATH, split='train')
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True,
                                               num_workers=workers, pin_memory=True)
    test_dataset = MasksDataset(data_folder=constants.TEST_IMG_PATH, split='test')
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False,
                                              num_workers=workers, pin_memory=True)

    # Calculate total number of epochs to train and the epochs to decay learning rate at
    # (i.e. convert iterations to epochs)
    # To convert iterations to epochs, divide iterations by the number of iterations per epoch
    # The paper trains for 120,000 iterations with a batch size of 32, decays after 80,000 and 100,000 iterations
    epochs = 100  # TODO change

    train_losses = []

    # Epochs
    for epoch in range(start_epoch, epochs):
        # One epoch's training
        epoch_loss = train(train_loader=train_loader,
                           model=model,
                           criterion=criterion,
                           optimizer=optimizer,
                           epoch=epoch)
        # Get the epoch loss and append to list
        train_losses.append(epoch_loss)
        # Save all the losses to pickled list
        with open('/home/student/train_losses_list.pkl', 'wb') as f:
            pickle.dump(train_losses, f)

        # Save checkpoint
        save_checkpoint(epoch, model)

        # Evaluate test set
        # TODO Add the new evaluate() function here


def train(train_loader, model, criterion, optimizer, epoch):
    """
    One epoch's training.

    :param train_loader: DataLoader for training data
    :param model: model
    :param criterion: MultiBox loss
    :param optimizer: optimizer
    :param epoch: epoch number
    """
    model.train()  # training mode enables dropout

    batch_time = AverageMeter()  # forward prop. + back prop. time
    data_time = AverageMeter()  # data loading time
    losses = AverageMeter()  # loss

    start = time.time()

    # Batches
    for i, (images, boxes, labels) in enumerate(train_loader):
        data_time.update(time.time() - start)
        # Move to default device
        images = images.to(device)  # (batch_size (N), 3, 300, 300)
        boxes = boxes.to(device)
        labels = labels.to(device)

        # predicted
        ploc, plabel = model(images)  # ploc, plabel: Nx4x8732, Nxlabel_numx8732

        # ground truth
        gloc = boxes.expand(-1, 8732, 4).reshape(-1, 4, 8732).to(device)  # Nx4x8732
        glabel = labels.expand(-1, 8732).to(device)  # Nx8732

        # loss
        # add small constant to avoid 'inf' if one of bbox components is 0
        loss = criterion(ploc, plabel, gloc, glabel)

        # Backward prop.
        optimizer.zero_grad()
        loss.backward()

        # Clip gradients, if necessary
        if grad_clip is not None:
            clip_gradient(optimizer, grad_clip)

        # Update model
        optimizer.step()

        losses.update(loss.item(), images.size(0))
        batch_time.update(time.time() - start)

        start = time.time()

        # Print status
        if (i % print_freq == 0 or i == len(train_loader) - 1) & i != 0:
            print('Epoch: [{0}][{1}/{2}]\t'
                  'Batch Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                  'Data Time {data_time.val:.3f} ({data_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} ({loss.avg:.4f})\t'.format(epoch, i, len(train_loader),
                                                                  batch_time=batch_time,
                                                                  data_time=data_time, loss=losses))
    del ploc, plabel, images, boxes, labels  # free some memory since their histories may be stored

    return losses.avg


# TODO
#  1. Add early stopping based on test metrics / loss

if __name__ == '__main__':
    main()