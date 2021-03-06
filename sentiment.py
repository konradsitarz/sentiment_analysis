# -*- coding: utf-8 -*-
"""sentiment.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1JvhCZHcg4oSlaoRnpI7uhjDEwLZU1WSc
"""

!pip install torchmetrics

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report, 
    plot_confusion_matrix, 
    plot_roc_curve,
    ConfusionMatrixDisplay, 
    RocCurveDisplay
)
from tqdm.auto import tqdm

import pandas as pd
import numpy as np
import tensorflow as tf
from matplotlib import pyplot as plt

df = pd.read_csv('IMDB Dataset.csv')
df.head()

len(df)

X = df.review
y = df.sentiment.replace({'positive': 1, 'negative': 0})

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y)

tfidf = TfidfVectorizer(
    strip_accents=None,
    lowercase=False,
    preprocessor=None,
    use_idf=True,
    norm='l2',
    smooth_idf=True,
    min_df=0.0,
    max_df=1.0,
    stop_words='english'
)

X_train = tfidf.fit_transform(X_train)
X_test = tfidf.transform(X_test)

def train_eval_model(model):
  model.fit(X_train, y_train)
  y_pred = model.predict(X_test)
  print(classification_report(y_test, y_pred))
  fig, axes = plt.subplots(nrows=2, figsize=(20, 20))
  plot_confusion_matrix(model, X_test, y_test, ax=axes[0])
  plot_roc_curve(model, X_test, y_test, ax=axes[1])
  return axes

"""# Modele ML"""

model = LogisticRegression()
train_eval_model(model)

model = SGDClassifier(
    early_stopping=True
)
train_eval_model(model)

model = RandomForestClassifier(
    n_estimators=250,
    max_depth=3
)
train_eval_model(model)



"""# Sieć neuronowa"""

import torch
import torchtext
from torch import nn

max_len = 256
min_freq = 5
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

tokenizer = torchtext.data.utils.get_tokenizer('basic_english')

def tokenize(sample):
  return tokenizer(sample)[:max_len]

X_tokenized = X.map(tokenize).values
X_train, X_test, y_train, y_test = train_test_split(X_tokenized, y, test_size=0.2, stratify=y)
X_train, X_validation, y_train, y_validation = train_test_split(X_train, y_train, test_size=0.1, stratify=y_train)

special_tokens = ['<unk>', '<pad>']
vocab = torchtext.vocab.build_vocab_from_iterator(X_train,
                                                  min_freq=min_freq,
                                                  specials=special_tokens)

unk_index = vocab['<unk>']
pad_index = vocab['<pad>']
vocab.set_default_index(unk_index)

def tokens_to_ids(sample):
  ids = [vocab[token] for token in sample]
  ids += [pad_index] * (max_len - len(ids))
  return ids

X_train = np.stack(pd.Series(X_train).map(tokens_to_ids).values)
X_validation = np.stack(pd.Series(X_validation).map(tokens_to_ids).values)
X_test = np.stack(pd.Series(X_test).map(tokens_to_ids).values)

X_train.shape

X_validation.shape

X_test.shape

class CNN(nn.Module):
    def __init__(self, vocab_size, embedding_dim, n_filters, filter_sizes, output_dim, dropout_rate, 
                 pad_index):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_index)
        self.convs = nn.ModuleList([nn.Conv1d(embedding_dim, 
                                              n_filters, 
                                              filter_size) 
                                    for filter_size in filter_sizes])
        self.fc = nn.Linear(len(filter_sizes) * n_filters, output_dim)
        self.dropout = nn.Dropout(dropout_rate)
        
    def forward(self, ids):
        # ids = [batch size, seq len]
        embedded = self.dropout(self.embedding(ids))
        # embedded = [batch size, seq len, embedding dim]
        embedded = embedded.permute(0,2,1)
        # embedded = [batch size, embedding dim, seq len]
        conved = [torch.relu(conv(embedded)) for conv in self.convs]
        # conved_n = [batch size, n filters, seq len - filter_sizes[n] + 1]
        pooled = [conv.max(dim=-1).values for conv in conved]
        # pooled_n = [batch size, n filters]
        cat = self.dropout(torch.cat(pooled, dim=-1))
        # cat = [batch size, n filters * len(filter_sizes)]
        prediction = self.fc(cat)
        # prediction = [batch size, output dim]
        return prediction

def get_accuracy(y_hat, label):
    batch_size, _ = y_hat.shape
    y_hat[y_hat > 0.5] = 1
    y_hat[y_hat <= 0.5] = 0
    correct_predictions = y_hat.eq(label).sum()
    accuracy = correct_predictions / batch_size
    return accuracy

def train(model, criterion, optimizer, data):
  epoch_loss_train = []
  epoch_acc_train = []

  model.train()

  for batch_x, batch_y in tqdm(data, desc='Train'):
    optimizer.zero_grad()

    ids = batch_x.to(device)
    labels = batch_y.to(device).reshape(-1, 1).float()

    prediction = model(ids)
    loss = criterion(prediction, labels)
    prediction = torch.sigmoid(prediction)
    accuracy = get_accuracy(prediction, labels)
    loss.backward()
    optimizer.step()
    epoch_loss_train.append(loss.item())
    epoch_acc_train.append(accuracy.item())
  return epoch_loss_train, epoch_acc_train


def evaluate(model, criterion, optimizer, data):
  epoch_loss_validation = []
  epoch_acc_validation = []

  model.eval()
  with torch.no_grad():

    for batch_x, batch_y in tqdm(data, desc='Validation'):
      ids = batch_x.to(device)
      labels = batch_y.to(device).reshape(-1, 1).float()

      prediction = model(ids)
      loss = criterion(prediction, labels)
      prediction = torch.sigmoid(prediction)
      accuracy = get_accuracy(prediction, labels)

      epoch_loss_validation.append(loss.item())
      epoch_acc_validation.append(accuracy.item())
  return epoch_loss_validation, epoch_acc_validation

def train_eval_nn_model(model, criterion, optimizer, train_dataloader, valid_dataloader):
  loss_train = []
  acc_train = []
  loss_valid = []
  acc_valid = []
  best_valid_loss = float('inf')
  early_stopping_counter = 0
  early_stopping_limit = 3

  for epoch in tqdm(range(n_epochs), desc='Epochs'):
    epoch_loss_train, epoch_acc_train = train(model, criterion, optimizer, train_dataloader)
    epoch_loss_valid, epoch_acc_valid = evaluate(model, criterion, optimizer, valid_dataloader)

    loss_train.extend(epoch_loss_train)
    acc_train.extend(epoch_acc_train)
    loss_valid.extend(epoch_loss_valid)
    acc_valid.extend(epoch_acc_valid)

    val_loss = np.mean(epoch_loss_valid)
    if val_loss < best_valid_loss:
      print(f'Saving model with loss: {val_loss}')
      best_valid_loss = val_loss
      early_stopping_counter = 0
      torch.save(model, 'sentiment.torch')
    else:
      early_stopping_counter += 1
    
    if early_stopping_counter >= early_stopping_limit:
      print(f'Early stopping because of {early_stopping_limit} epochs without improvement')
      break

  return best_valid_loss, plot_model_stats(loss_train, loss_valid, acc_train, acc_valid)

def plot_model_stats(loss_train, loss_valid, acc_train, acc_valid):
  fig, axes = plt.subplots(nrows=2, ncols=2, figsize=(20, 14))
  axes[0][0].plot(loss_train)
  axes[0][0].set_title('Training loss')

  axes[1][0].plot(loss_valid)
  axes[1][0].set_title('Validation loss')

  axes[0][1].plot(acc_train)
  axes[0][1].set_title('Accuracy training')

  axes[1][1].plot(acc_valid)
  axes[1][1].set_title('Accuracy validation')
  plt.show()
  return axes

def process_sentence(sentence, model):
  tokens = tokenize(sentence)
  ids = tokens_to_ids(tokens)
  pred = torch.sigmoid(model(torch.tensor(ids).to(device).reshape(1, -1))).item()
  return pred

def train_and_check_model(embedding_dim=300, n_filters=100, filter_sizes=[3,5,7], dropout_rate=0.25, batch_size=1024):
  vocab_size = len(vocab)
  output_dim = 1

  model = CNN(vocab_size, embedding_dim, n_filters, filter_sizes, output_dim, dropout_rate, pad_index)
  optimizer = torch.optim.Adam(model.parameters())
  criterion = nn.BCEWithLogitsLoss()
  device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

  model = model.to(device)
  criterion = criterion.to(device)

  train_dataloader = torch.utils.data.DataLoader(
      list(zip(X_train, y_train)),
      batch_size=batch_size
  )
  valid_dataloader = torch.utils.data.DataLoader(
      list(zip(X_validation, y_validation)),
      batch_size=batch_size
  )
  test_dataloader = torch.utils.data.DataLoader(
      list(zip(X_test, y_test)),
      batch_size=batch_size
  )
  return model, train_eval_nn_model(model, criterion, optimizer, train_dataloader, valid_dataloader)

"""## Wybranie hiperparametrów"""

params = [
  # baseline
  dict(
    embedding_dim = 300,
    n_filters = 100,
    filter_sizes = [3,5,7],
    dropout_rate = 0.25,
    batch_size = 1024
  ),
  # more filters
  dict(
    embedding_dim = 300,
    n_filters = 200,
    filter_sizes = [3,5,7],
    dropout_rate = 0.25,
    batch_size = 1024
  ),
  # higher embedding dim
  dict(
    embedding_dim = 1000,
    n_filters = 100,
    filter_sizes = [3,5,7],
    dropout_rate = 0.25,
    batch_size = 1024
  )
]

n_epochs = 20

for param in params:
  model, (valid_loss, plots) = train_and_check_model(**param)
  print(f'params {param}')
  print(f'valid loss = {valid_loss}')

"""Najlepszy loss na zbiorze walidacyjnym wyszedł przy pierwszym setcie parametrów. """

model, (val_loss, plots) = train_and_check_model(**{'embedding_dim': 300, 'n_filters': 100, 'filter_sizes': [3, 5, 7], 'dropout_rate': 0.25, 'batch_size': 1024})



"""## Test i podsumowanie"""

test_dataloader = torch.utils.data.DataLoader(
    list(zip(X_test, y_test)),
    batch_size=1024
)

epoch_loss_validation = []
epoch_acc_validation = []
predictions = []
predictions_binary = []
y_true = []

model.eval()
with torch.no_grad():
  for batch_x, batch_y in tqdm(test_dataloader, desc='Test'):
    ids = batch_x.to(device)
    labels = batch_y.to(device).reshape(-1, 1).float()

    prediction = model(ids)
    prediction = torch.sigmoid(prediction).cpu().detach().numpy()[:, 0]
    prediction_binary = prediction.copy()
    prediction_binary[prediction < 0.5] = 0
    prediction_binary[prediction >= 0.5] = 1
    predictions.extend(prediction)
    predictions_binary.extend(prediction_binary)
    y_true.extend(labels.cpu().detach().numpy()[:, 0])

fig, axes = plt.subplots(nrows=2, figsize=(20, 20))
ConfusionMatrixDisplay.from_predictions(y_true, predictions_binary, ax=axes[0])
RocCurveDisplay.from_predictions(y_true, predictions, ax=axes[1])

sentence = 'This movie was so boring I slept well on it.'
process_sentence(sentence, model)

