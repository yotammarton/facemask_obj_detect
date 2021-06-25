import argparse
import torch.utils.data
from dataset import MasksDataset
import torchvision
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from eval import evaluate


def collate_fn(batch):
    return tuple(zip(*batch))


# Parsing script arguments
parser = argparse.ArgumentParser(description='Process input')
parser.add_argument('input_folder', type=str, help='Input folder path, containing images')
args = parser.parse_args()

# Define device and checkpoint path
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

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

mean = [0.5244, 0.4904, 0.4781]
std = [0.2642, 0.2608, 0.2561]

checkpoint = torch.load('/home/student/facemask_obj_detect/fastrcnn/checkpoint_fasterrcnn_epoch=4.pth.tar')  # TODO
model = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=False,
                                                             pretrained_backbone=False,
                                                             image_mean=mean,
                                                             image_std=std,
                                                             min_size=300,
                                                             max_size=300).to(device)
in_features = model.roi_heads.box_predictor.cls_score.in_features
model.roi_heads.box_predictor = FastRCNNPredictor(in_features, n_classes).to(device)
model.load_state_dict(checkpoint['state_dict'])

# Load data
dataset = MasksDataset(data_folder=args.input_folder, split='test')
dataloader = torch.utils.data.DataLoader(dataset, batch_size=20, shuffle=False,
                                         num_workers=1, pin_memory=False, collate_fn=collate_fn)

# Evaluate model on given data
print(f"Evaluating data from path {args.input_folder}")
evaluate(dataloader, model, save_csv="prediction.csv", verbose=True)
