import torch
import pandas as pd
from train_util import AddEgoIds, extract_param, add_arange_ids, get_loaders, evaluate_homo, evaluate_hetero
from training import get_model
from torch_geometric.nn import to_hetero, summary
import wandb
import logging
import os
import sys
import time
import json

script_start = time.time()

def infer_gnn(tr_data, val_data, te_data, tr_inds, val_inds, te_inds, args, data_config):
    #set device
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    #define a model config dictionary and wandb logging at the same time
    wandb.init(
        mode="disabled" if args.testing else "online",
        project="your_proj_name",

        config={
            "epochs": args.n_epochs,
            "batch_size": args.batch_size,
            "model": args.model,
            "data": args.data,
            "num_neighbors": args.num_neighs,
            "lr": extract_param("lr", args),
            "n_hidden": extract_param("n_hidden", args),
            "n_gnn_layers": extract_param("n_gnn_layers", args),
            "loss": "ce",
            "w_ce1": extract_param("w_ce1", args),
            "w_ce2": extract_param("w_ce2", args),
            "dropout": extract_param("dropout", args),
            "final_dropout": extract_param("final_dropout", args),
            "n_heads": extract_param("n_heads", args) if args.model == 'gat' else None
        }
    )

    config = wandb.config

    #set the transform if ego ids should be used
    if args.ego:
        transform = AddEgoIds()
    else:
        transform = None

    #add the unique ids to later find the seed edges
    add_arange_ids([tr_data, val_data, te_data])

    tr_loader, val_loader, te_loader = get_loaders(tr_data, val_data, te_data, tr_inds, val_inds, te_inds, transform, args)

    #get the model
    sample_batch = next(iter(tr_loader))
    model = get_model(sample_batch, config, args)

    if args.reverse_mp:
        model = to_hetero(model, te_data.metadata(), aggr='mean')
    
    # if not (args.avg_tps or args.finetune):
    #     command = " ".join(sys.argv)
    #     name = ""
    #     name = '-'.join(name.split('-')[3:])
    #     args.unique_name = name
    args.unique_name = 'True'

    logging.info("=> loading model checkpoint")
    checkpoint = torch.load(f'{data_config["paths"]["model_to_load"]}/checkpoint_{args.unique_name}.tar')
    start_epoch = checkpoint['epoch']
    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)

    logging.info("=> loaded checkpoint (epoch {})".format(start_epoch))

    if not args.reverse_mp:
        te_f1, te_prec, te_rec, te_acc, te_tp, te_tn, te_fp, te_fn = evaluate_homo(te_loader, te_inds, model, te_data, device, args)
    else:
        te_f1, te_prec, te_rec, te_acc, te_tp, te_tn, te_fp, te_fn = evaluate_hetero(te_loader, te_inds, model, te_data, device, args)

    result = {
        'F1': te_f1,
        'Precision': te_prec,
        'Recall': te_rec,
        'Accuracy': te_acc,
        'True Positives': te_tp,
        'True Negatives': te_tn,
        'False Positives': te_fp,
        'False Negatives': te_fn
    }
    logging.info(json.dumps(result))

    wandb.finish()