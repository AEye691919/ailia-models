import sys
import time

import torch
import numpy
from transformers import BertTokenizer, BertJapaneseTokenizer

import ailia

sys.path.append('../../util')
from utils import get_base_parser, update_parser  # noqa: E402
from model_utils import check_and_download_models  # noqa: E402


# ======================
# Arguemnt Parser Config
# ======================

MODEL_LISTS = [
    'bert-base-cased',
    'bert-base-uncased',
    'bert-base-japanese-whole-word-masking'
]

NUM_PREDICT = 5

SENTENCE = '私は[MASK]で動く。'


parser = get_base_parser('bert masklm sample.', None, None)
# overwrite
parser.add_argument(
    '--input', '-i', metavar='TEXT',
    default=SENTENCE,
    help='input text'
)
parser.add_argument(
    '-a', '--arch', metavar='ARCH',
    default='bert-base-japanese-whole-word-masking', choices=MODEL_LISTS,
    help='model lists: ' + ' | '.join(MODEL_LISTS)
)
args = update_parser(parser)


# ======================
# PARAMETERS
# ======================

WEIGHT_PATH = args.arch+".onnx"
MODEL_PATH = args.arch+".onnx.prototxt"
REMOTE_PATH = "https://storage.googleapis.com/ailia-models/bert_maskedlm/"


# ======================
# Main function
# ======================
def main():
    # model files check and download
    check_and_download_models(WEIGHT_PATH, MODEL_PATH, REMOTE_PATH)

    if args.arch == 'bert-base-cased' or args.arch == 'bert-base-uncased':
        tokenizer = BertTokenizer.from_pretrained(args.arch)
    else:
        tokenizer = BertJapaneseTokenizer.from_pretrained(
            'cl-tohoku/'+'bert-base-japanese-whole-word-masking'
        )
    text = args.input
    print("Input text : "+text)

    tokenized_text = tokenizer.tokenize(text)
    print("Tokenized text : ", tokenized_text)

    masked_index = -1
    for i in range(0, len(tokenized_text)):
        if tokenized_text[i] == '[MASK]':
            masked_index = i
            break
    if masked_index == -1:
        print("[MASK] not found")
        sys.exit(1)

    indexed_tokens = tokenizer.convert_tokens_to_ids(tokenized_text)
    print("Indexed tokens : ", indexed_tokens)

    ailia_model = ailia.Net(MODEL_PATH, WEIGHT_PATH, env_id=args.env_id)

    indexed_tokens = numpy.array(indexed_tokens)
    token_type_ids = numpy.zeros((1, len(tokenized_text)))
    attention_mask = numpy.zeros((1, len(tokenized_text)))
    attention_mask[:, 0:len(tokenized_text)] = 1

    inputs_onnx = {
        "token_type_ids": token_type_ids,
        "input_ids": indexed_tokens,
        "attention_mask": attention_mask,
    }

    print("Predicting...")
    if args.benchmark:
        print('BENCHMARK mode')
        for i in range(5):
            start = int(round(time.time() * 1000))
            outputs = ailia_model.predict(inputs_onnx)
            end = int(round(time.time() * 1000))
            print("\tailia processing time {} ms".format(end - start))
    else:
        outputs = ailia_model.predict(inputs_onnx)

    predictions = torch.from_numpy(
        outputs[0][0, masked_index]).topk(NUM_PREDICT)

    print("Predictions : ")
    for i, index_t in enumerate(predictions.indices):
        index = index_t.item()
        token = tokenizer.convert_ids_to_tokens([index])[0]
        print(i, token)

    print('Script finished successfully.')


if __name__ == "__main__":
    main()
