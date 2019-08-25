'''
Test that the forward pass I implemented lead to identical results to that of
the original code release. The tf code here is a direct copy and paste from
here:
https://github.com/xiangwang1223/neural_graph_collaborative_filtering/blob/master/NGCF/utility/metrics.py
'''

import numpy as np
import tensorflow as tf
import torch
import torch.nn.functional as F

from torch import nn
import pdb


np.random.seed(1)
n_users = 100
n_items = 200
n_emb = 24
w1_units = [12, 6]
w2_units = [12, 6]
n_layers = len(w1_units)
R = np.random.choice(2, (300, 300), p=[0.8,0.2])
A = torch.from_numpy(R)

# ----------
# PYTORCH
# ----------
embeddings_user = torch.from_numpy(np.random.rand(n_users, n_emb)).float()
embeddings_item = torch.from_numpy(np.random.rand(n_items, n_emb)).float()

features = [n_emb] + w1_units
W1 = nn.ModuleList()
W2 = nn.ModuleList()
for i in range(1,len(features)):

    w1 = torch.rand(features[i-1],features[i]).t()
    b1 = torch.rand(features[i])
    w2 = torch.rand(features[i-1],features[i]).t()
    b2 = torch.rand(features[i])

    W1.append(nn.Linear(features[i-1],features[i]))
    W2.append(nn.Linear(features[i-1],features[i]))

    W1[i-1].weight = nn.Parameter(w1)
    W1[i-1].bias = nn.Parameter(b1)
    W2[i-1].weight = nn.Parameter(w2)
    W2[i-1].bias = nn.Parameter(b2)

def torch_forward():

    ego_embeddings = torch.cat([embeddings_user, embeddings_item], 0)
    pred_embeddings = [ego_embeddings]

    for k in range(n_layers):

        weighted_sum_emb = torch.mm(A.float(), ego_embeddings.float())
        affinity_emb = ego_embeddings.mul(weighted_sum_emb)

        t1 = W1[k](weighted_sum_emb)
        t2 = W2[k](affinity_emb)

        ego_embeddings = F.leaky_relu(t1 + t2)
        norm_embeddings = F.normalize(ego_embeddings, p=2, dim=1)

        pred_embeddings += [norm_embeddings]

    pred_embeddings = torch.cat(pred_embeddings, 1)
    u_g_embeddings, i_g_embeddings = pred_embeddings.split([n_users, n_items], 0)
    return u_g_embeddings, i_g_embeddings

torch_u_g_emb, torch_i_g_emb = torch_forward()

from test_bpr_loss import torch_bpr_loss

np.random.seed(2)
u = np.random.choice(n_users, 50)
i = np.random.choice(n_items, 50)
tmp = np.setdiff1d(np.arange(n_items), i)
j = np.random.choice(tmp, 50)

torch_u_emb =  torch_u_g_emb[u]
torch_p_emb =  torch_i_g_emb[i]
torch_n_emb =  torch_i_g_emb[j]

torch_loss = torch_bpr_loss(torch_u_emb,torch_p_emb,torch_n_emb)

# ----------
# TF
# ----------
tf.enable_eager_execution()

weights ={}
weights['user_embedding'] = tf.convert_to_tensor(embeddings_user.numpy())
weights['item_embedding'] = tf.convert_to_tensor(embeddings_item.numpy())

for i in range(1,len(features)):
    weights['W_gc_%d' % (i-1)] = tf.convert_to_tensor(W1[i-1].weight.t().detach().numpy())
    weights['b_gc_%d' % (i-1)] = tf.convert_to_tensor(W1[i-1].bias.detach().numpy())
    weights['W_bi_%d' % (i-1)] = tf.convert_to_tensor(W2[i-1].weight.t().detach().numpy())
    weights['b_bi_%d' % (i-1)] = tf.convert_to_tensor(W2[i-1].bias.detach().numpy())

A = tf.convert_to_tensor(A.float().numpy())

# The original code stars like this
        # # Generate a set of adjacency sub-matrix.
        # if self.node_dropout_flag:
        #     # node dropout.
        #     A_fold_hat = self._split_A_hat_node_dropout(self.norm_adj)
        # else:
        #     A_fold_hat = self._split_A_hat(self.norm_adj)

        # ego_embeddings = tf.concat([self.weights['user_embedding'], self.weights['item_embedding']], axis=0)

        # all_embeddings = [ego_embeddings]

        # for k in range(0, self.n_layers):

        #     temp_embed = []
        #     for f in range(self.n_fold):
        #         temp_embed.append(tf.sparse_tensor_dense_matmul(A_fold_hat[f], ego_embeddings))

        #     # sum messages of neighbors.
        #     side_embeddings = tf.concat(temp_embed, 0)

# But here we will not be using dropout and A is small enough so we can directly do:
#         side_embeddings = tf.matmul(A, ego_embeddings)
# From there on is the same
def tf_forward():

    ego_embeddings = tf.concat([weights['user_embedding'], weights['item_embedding']], axis=0)
    all_embeddings = [ego_embeddings]

    for k in range(0, n_layers):

        side_embeddings = tf.matmul(A, ego_embeddings)
        bi_embeddings = tf.multiply(ego_embeddings, side_embeddings)

        sum_embeddings = tf.nn.leaky_relu(
            tf.matmul(side_embeddings, weights['W_gc_%d' % k]) + weights['b_gc_%d' % k])
        bi_embeddings = tf.nn.leaky_relu(
            tf.matmul(bi_embeddings, weights['W_bi_%d' % k]) + weights['b_bi_%d' % k])

        ego_embeddings = sum_embeddings + bi_embeddings
        norm_embeddings = tf.math.l2_normalize(ego_embeddings, axis=1)

        all_embeddings += [norm_embeddings]

    all_embeddings = tf.concat(all_embeddings, 1)
    u_g_embeddings, i_g_embeddings = tf.split(all_embeddings, [n_users, n_items], 0)
    return u_g_embeddings, i_g_embeddings

tf_u_g_emb, tf_i_g_emb = tf_forward()

from test_bpr_loss import tf_bpr_loss

np.random.seed(2)
u = np.random.choice(n_users, 50)
i = np.random.choice(n_items, 50)
tmp = np.setdiff1d(np.arange(n_items), i)
j = np.random.choice(tmp, 50)

tf_u_emb =  tf.gather(tf_u_g_emb, u)
tf_p_emb =  tf.gather(tf_i_g_emb, i)
tf_n_emb =  tf.gather(tf_i_g_emb, j)

tf_loss = tf_bpr_loss(tf_u_emb,tf_p_emb,tf_n_emb)

print(np.array(tf_loss), torch_loss.detach().numpy())