import itertools
import copy
import collections
import numpy as np
from numpy.random import default_rng
import matplotlib.pyplot as plt
import torch
from torch.utils.data import Dataset, DataLoader, random_split
import torch.nn as nn
import pickle
import random
from sklearn.model_selection import train_test_split

######################
### Generate sequences
######################

convert_inputcue = {'A': 1, 
                    'B': 2,
                    'C': 3,
                    'D': 4,
                    'E': 5, 
                    'F': 6,
                    'G': 7,
                    'H': 8}

convert_operation = {'+': 9,
                     '*': 10,
                     '-': 11,
                     '%': 12}

default_cues = {'A': 2, 
                'B': 3,
                'C': 5,
                'D': 7,
                'E': 1, 
                'F': 4,
                'G': 9,
                'H': 11}

def generate_trials(operators, input_ids, len_seq,\
                    init_values, rand, rep):
    
    ''' This function defines all possible permutations of initial value & sequence of input cues and operators.
    Args: 
        operators, input_ids, init_values: lists of operator, input cue and initial values
        len_seq: number of operation and input pairs per sequence
        replacement: whether an operation/input can be repeated in a sequence
    Returns:
        Output is an array of shape n X len_seq+1.
        Each row is one of n unique ordered permutations.
        First column indicates the initial value at t=0.
        Every following column contains a tuple, where the first position indicates
        the operator and the second position indicates the input cue.
        Final column indicates the outcome of the opperatioons on the initial value'''
    
    seq = []
    combi_operators = list(itertools.product(operators, repeat=len_seq))*rep
    if rand:
        for op in combi_operators:
            cue = random.choices(input_ids, k=2)
            seq.append([random.choice(init_values),
                        *zip(tuple(op), tuple(cue))]) #group per time point t
        
    else:
        combi_inputcue = list(itertools.product(input_ids, repeat=len_seq))
        for init in init_values:
            for cue in combi_inputcue:
                for op in combi_operators:
                    seq.append([init,
                                *zip(tuple(op), cue)]) #group per time point t

    return seq

def operate_op(currval, step_tuple, cue_dict):
    """ Function applies operations to input value
    Args:
        ...
    Returns:
        ...
    """
    if not cue_dict:
        nextval = step_tuple[1]
    else:
        nextval = cue_dict[step_tuple[1]]
    if step_tuple[0] == '+': # add
        currval = currval + nextval
    elif step_tuple[0] == '*': # multiply
        currval = currval * nextval
    return currval

def calculate_output(step_tuple, cue_dict, bidmas):
    """ Function applies operations to input value
    Args:
        ...
    Returns:
        ...
    """
    if bidmas:
        calc_string = str(step_tuple[0])
        if not cue_dict:
            for i in range(1,len(step_tuple)):
                calc_string = calc_string + step_tuple[i][0] + str(step_tuple[i][1])
        else:
            for i in range(1,len(step_tuple)):
                calc_string = calc_string + step_tuple[i][0] + str(cue_dict[step_tuple[i][1]])
        curr_val = eval(calc_string)
    
    else:
        curr_val = step_tuple[0]
        for i in range(1,len(step_tuple)):
            curr_val = operate_op(curr_val, step_tuple[i], cue_dict)
    return curr_val


def generate_sequences(operators, input_ids, len_seq, cue_dict = default_cues,\
                       init_values = list(range(1,6)), rand=True, rep = 1, bidmas = False):
    """ Function applies operations to input value
    Args:
        ...
    Returns:
        ...
    """
    all_trials = generate_trials(operators, input_ids, len_seq, init_values, rand, rep)
    for trial in all_trials:
        trial_output = calculate_output(trial, cue_dict, bidmas)
        trial.append(trial_output)
    
    return(all_trials)
      
      
##################################################
## Transform data to rnn data
##################################################


class SequenceData(Dataset):
    def __init__(self, data, labels, seq_len, stages, cont_out, primitive_type):

        self.data = convert_seq2onehot(data, stages, primitive_type)
        self.seq_len = seq_len
        if cont_out:
            self.labels = labels
        else:
            self.labels = convert_outs2labels(labels)
            
    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        sequence = self.data[index,:].astype(np.float32)
        out_state = np.array(self.labels[index]).astype(np.float32)
        return sequence, out_state
    
    
def convert_seq2inputs(sequences, seq_len=5, stages = False, cont_out = True, num_classes=13, primitive_type = False):
    '''
    Function converts sequences as they are generated by generate_experiment_lists.py
    into input to be fed into RNN (one-hote encoded)
    Parameters:
        sequences: list of trials with format : [initial_value, (operation, input_cue) ... , output_value]
        num_classes: total number of features for onehot encoding
        seq_len: number of time steps per sequence
        stages: if False each unit is a time step, if True each tuple is a time step
        cont_out: if True the output is continuous, if False output is categorical
    ''' 
    seq = [sublist[:-1] for sublist in sequences]
    out = [sublist[-1] for sublist in sequences]
    
    seqdata = SequenceData(seq, out, seq_len, stages, cont_out, primitive_type)

    return seqdata


def convert_seq2onehot(seq, stages, primitive_type, num_classes=13):
    """ Function ...
    Args:
        ...
    Returns:
        ...
    """
    data = []

    for trial in seq:
        trial_data = []
        for i,t in enumerate(trial):
            if i==0:
                init = torch.zeros(num_classes)
                init[0] = t
                trial_data.append(init)
                continue
            else:
                op = torch.tensor(convert_operation[t[0]])
                op = torch.nn.functional.one_hot(op, num_classes=num_classes)
                if not primitive_type:
                    inputcue = torch.tensor(convert_inputcue[t[1]])
                    inputcue = torch.nn.functional.one_hot(inputcue, num_classes=num_classes)
                elif primitive_type == 'op':
                    inputcue = torch.zeros(num_classes)
                    inputcue[0] = t[1]
                if stages:
                    op_cue = op + inputcue
                    trial_data.append(op_cue)
                else:
                    trial_data.append(op)
                    trial_data.append(inputcue)
        data.append(torch.stack(trial_data))

    data = torch.stack(data,dim=0) #combine into tensor of shape n_trials X n_time_steps X inputvector_size
    data = data.numpy()

    return data


def convert_outs2labels(outputs, num_outs=1000):
    """ Function ...
    Args:
        ...
    Returns:
        ...
    """
    all_outs = []
    for out in outputs:
        out = torch.tensor(out)
        onehot_out = torch.nn.functional.one_hot(out, num_classes = num_outs)
        all_outs.append(onehot_out)
    return all_outs
