import torch
import numpy as np
import sys
import librosa
import argparse
import time
import pyaudio

import ailia
"""import original modules"""
#sys.path.append('./ailia-models/util') 
#from model_utils import check_and_download_models

#librispeech_pretrained_v2
#how strange it seemed to the sad woman as she watched the growth and the beauty that became every day more brilliant and the intelligence that through its quivering sunshine over the tiny features of this child

#an4_pretrained_v2
# sthiee sixtysx s one cs one stwp teoh ten teny kwenth three t four eineaieteen twonr two seven te ine  thine shirn i np twe tseiox sven sie

#ted_pretrained_v2
#howstrange at seemed to the sad woman she wachd the grolt han the beauty that became every day more brilliant and the intelligence that through its equivering sunching over the tiny peacturs of this child

#

# ======================
# Parameters
# ======================
WEIGHT_PATH = 'ted_pretrained_v2.onnx' #'deepspeech2_dynamic.onnx'
MODEL_PATH = 'ted_pretrained_v2.onnx.prototxt' #'deepspeech2_dynamic.onnx.prototxt'
REMOTE_PATH = 'https://storage.googleapis.com/ailia-models/deepspeech2/'

WAV_PATH = './1221-135766-0000.wav'
SAVE_TEXT_PATH = 'output.txt'

SAMPLING_RATE = 16000
WIN_LENGTH = int(SAMPLING_RATE * 0.02)
HOP_LENGTH = int(SAMPLING_RATE * 0.01)

LABELS = list('_\'ABCDEFGHIJKLMNOPQRSTUVWXYZ ')
int_to_char = dict([(i, c) for (i, c) in enumerate(LABELS)])
BRANK_LABEL_INDEX = 0

#BeamCTCDecoder parameter
LM_PATH = '3-gram.pruned.3e-7.arpa'
ALPHA=1.97
BETA=4.36 
CUTOFF_TOP_N=40
CUTOFF_PROB=1.0
NUM_PROCESS=1
BEAM_WIDTH=128

#pyaudio
CHUNK = 1024
FORMAT = pyaudio.paInt16 
CHANNELS = 1             
RECODING_SAMPING_RATE = 48000        
THRESHOLD = 0.02

# ======================
# Arguemnt Parser Config
# ======================
parser = argparse.ArgumentParser(
    description='deepspeech2'
)
parser.add_argument(
    '-i', '--input', metavar='WAV',
    default=WAV_PATH,
    help='The input wav path.'
)
parser.add_argument(
    '-s', '--savepath', metavar='SAVE_TEXT_PATH',
    default=SAVE_TEXT_PATH,
    help='Save path for the output text.'
)
parser.add_argument(
    '-b', '--benchmark',
    action='store_true',
    help='Running the inference on the same input 5 times ' +
         'to measure execution performance. (Cannot be used in video mode)'
)
parser.add_argument(
    '-V',
    action='store_true',
    help='use microphone input'
)
parser.add_argument(
    '-d', '--beamdecode',
    action='store_true',
    help='use beam decoder'
)
parser.add_argument(
    '-a', metavar='WEIGHT',
    default=WEIGHT_PATH,
    help='The .onnx path.'
)

args = parser.parse_args()

# ======================
# Utils
# ======================
def create_spectrogram(wav):
    stft = librosa.stft(wav, n_fft=WIN_LENGTH,
                        win_length=WIN_LENGTH, hop_length=HOP_LENGTH,
                        window='hamming')
    stft, _ = librosa.magphase(stft)
    spectrogram = np.log1p(stft)
    spec_length = np.array(([stft.shape[1]-1]))

    mean = spectrogram.mean()
    std = spectrogram.std()
    spectrogram -= mean
    spectrogram /= std

    spectrogram = np.log1p(spectrogram)
    spectrogram = spectrogram[np.newaxis, np.newaxis, :, :]

    return (spectrogram, spec_length)


def record_microphone_input():
    print('Ready...')
    time.sleep(1)
    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RECODING_SAMPING_RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    #time.sleep(1)
    print("Please speak something")

    frames = []
    count_uv = 0

    stream.start_stream()
    while True:
        data = np.frombuffer(stream.read(CHUNK), dtype=np.int16) / 32768.0
        if data.max() > THRESHOLD:
            frames.extend(data)
            count_uv = 0
        elif len(frames) > 0:
            count_uv += 1
            if count_uv > 48:
                break
            frames.extend(data)
        

    #print("Translating")

    stream.stop_stream()
    stream.close()
    p.terminate()

    wav = np.array(frames)
    return librosa.resample(wav, RECODING_SAMPING_RATE, SAMPLING_RATE)


def decode(sequence, size=None):
    sequence = np.argmax(sequence, -1)
    
    text = ''
    size  = int(size[0]) if size is not None else len(sequence)
    for i in range(size):
        char = int_to_char[sequence[i]]
        if char != int_to_char[BRANK_LABEL_INDEX]:
            if i != 0 and char == int_to_char[sequence[i - 1]]:
                pass
            else:
                text += char
    return text.lower()


#言語モデルを使用したデコード
def beam_ctc_decode(sequence, size=None, decoder=None):
    out, scores, offsets, seq_len = decoder.decode(sequence, size)

    results = []
    for b, batch in enumerate(out):
        utterances = []
        for p, utt in enumerate(batch):
            size = seq_len[0][p]
            if size > 0:
                transcript = ''.join(map(lambda x: int_to_char[x.item()], utt[0:size]))
            else:
                transcript = ''
        utterances.append(transcript)

    return utterances[0].lower()


# ======================
# Main functions
# ======================
def wavfile_input_recognition():
    if args.beamdecode:
        try:
            from ctcdecode import CTCBeamDecoder
        except ImportError:
            raise ImportError("BeamCTCDecoder requires paddledecoder package.")

        decoder = CTCBeamDecoder(LABELS, LM_PATH, ALPHA, BETA, CUTOFF_TOP_N, CUTOFF_PROB, BEAM_WIDTH,
                                  NUM_PROCESS, BRANK_LABEL_INDEX)

    wav = librosa.load(args.input, sr=SAMPLING_RATE)[0]
    spectrogram = create_spectrogram(wav)

    # net initialize
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')
    net = ailia.Net(MODEL_PATH, WEIGHT_PATH, env_id=env_id)
    net.set_input_shape(spectrogram[0].shape)

    # inference
    print('Start inference...')
    if args.benchmark:
        print('BENCHMARK mode')
        for c in range(5):
            start = int(round(time.time() * 1000))
            preds_ailia, output_length = net.predict(spectrogram)
            end = int(round(time.time() * 1000))
            print("\tailia processing time {} ms".format(end-start))
    else:
        #Deep Speech output: output_probability, output_length
        preds_ailia, output_length = net.predict(spectrogram)

    #実装上、1度torch.Tensorに変換
    if args.beamdecode:
        text = beam_ctc_decode(torch.from_numpy(preds_ailia), torch.from_numpy(output_length), decoder)
    else:
        text = decode(preds_ailia[0], output_length)

    with open(args.savepath, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'predict sentence:\n{text}')
    print('Script finished successfully.')


# ======================
# microphone input mode
# ======================
def microphone_input_recognition():
    env_id = ailia.get_gpu_environment_id()
    print(f'env_id: {env_id}')

    if args.beamdecode:
        try:
            from ctcdecode import CTCBeamDecoder
        except ImportError:
            raise ImportError("BeamCTCDecoder requires paddledecoder package.")

        decoder = CTCBeamDecoder(LABELS, LM_PATH, ALPHA, BETA, CUTOFF_TOP_N, CUTOFF_PROB, BEAM_WIDTH,
                                  NUM_PROCESS, BRANK_LABEL_INDEX)

    while True:
        wav = record_microphone_input()
        spectrogram = create_spectrogram(wav)

        # net initialize
        net = ailia.Net(MODEL_PATH, WEIGHT_PATH, env_id=env_id)
        net.set_input_shape(spectrogram[0].shape)

        # inference
        print('Translating...')
        #Deep Speech output: output_probability, output_length
        preds_ailia, output_length = net.predict(spectrogram)

        if args.beamdecode:
            text = beam_ctc_decode(torch.from_numpy(preds_ailia), torch.from_numpy(output_length), decoder)
        else:
            text = decode(preds_ailia[0], output_length)

        print(f'predict sentence:\n{text}\n')
        time.sleep(1)


def main():
    global WEIGHT_PATH, MODEL_PATH
    if args.a != WEIGHT_PATH:
        WEIGHT_PATH = args.a
        MODEL_PATH = WEIGHT_PATH + '.prototxt'
    #check_and_download_models(WEIGHT_PATH, MODEL_PATH, REMOTE_PATH)
    #マイク入力モード
    if args.V:
        try:
            microphone_input_recognition()
        except KeyboardInterrupt:
            print('script finished successfully.')

    #音声ファイル入力モード
    else:
        wavfile_input_recognition()


if __name__=="__main__":
    main()