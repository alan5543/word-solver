import nltk
import requests
import math
from collections import Counter
import random
import string

BASE_URL = "https://wordle.votee.dev:8000"

nltk.download('words')  # To download the word list corpus
from nltk.corpus import words

# Create our word bank from the NLTK 'words' corpus
words_bank = words.words()


def filter_words_bank_by_length(word_list, word_length):
    """
        the function of filtering the word bank by selected word length
    """
    return [word.lower() for word in list(set(word_list)) if len(word) == word_length]


def calculate_entropy(word, letter_probability):
    """
        the function of calculating the entropy score of each word by its letter probabilities
    """
    return -sum(letter_probability[letter] * math.log2(letter_probability[letter]) for letter in set(word))


def get_high_entropy_word(word_list, top_n=3):
    """
        the function of selecting the highest entropy word with the most valuable information to filter the word bank fast.
        We add a top_n to add some randomness in our function to prevent it is too deterministic
    """
    # Find the letter probabilities across the words list
    letter_counts = Counter("".join(word_list))
    total_letters = sum(letter_counts.values())
    letter_probabilities = {letter: count / total_letters for letter, count in letter_counts.items()}

    def find_word_entropy(word):
        return calculate_entropy(word=word, letter_probability=letter_probabilities)

    # Sort the word entropy from highest to lowest
    word_list.sort(key=find_word_entropy, reverse=True)

    # Select the top entropy word
    top_n_entropy_words = word_list[:top_n]

    # random select a guess word
    return random.choice(top_n_entropy_words)


def get_api_feedback(mode, guess, word_length=None, seed=None, custom_word=None):
    """
        the function of handling api feedback
    """
    if mode == 'daily':
        url = f"{BASE_URL}/daily"
        params = {'guess': guess, 'size': word_length}

    elif mode == 'random':
        url = f"{BASE_URL}/random"
        params = {'guess': guess, 'size': word_length, 'seed': seed}

    elif mode == 'custom':
        url = f"{BASE_URL}/word/{custom_word}"
        params = {'guess': guess}

    else:
        raise ValueError(f"Invalid mode")

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error from API: {response.status_code} {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve the API: {e}")
        return None


def filter_words_bank_by_feedback(word_list, correct_positions, present_letters, absent_letters):
    """
        the function of filtering the word bank by the words signal we collected
    """
    new_word_list = []
    for word in word_list:
        # Skip the word if any absent letter is in the word
        if any(letter in word for letter in absent_letters):
            continue

        # Skip the word if the correct letter is in wrong
        if any(word[pos] != letter for pos, letter in correct_positions.items()):
            continue

        # Skip the word if the present letter is missing or it is in a wrong slot
        if any(letter not in word or any(word[slot] == letter for slot in slots) for letter, slots in
               present_letters.items()):
            continue

        # append the valid word
        new_word_list.append(word)

    # return the filtered word bank
    return new_word_list


def generate_random_words_with_constraints(word_length, correct_positions, present_letters, absent_letters, num_words=1000):
    """
        Extending the word bank by combining the randomized letters and the word signals
    """
    word_list = []
    alphabet = list(set(string.ascii_lowercase) - set(absent_letters)) # Exclude the absent letters

    while len(word_list) < num_words:
        word = [''] * word_length

        # Place the correct letters in the correct position
        for pos, letter in correct_positions.items():
            word[pos] = letter

        # Place the present letters in the positions they have not been
        for letter, slots in present_letters.items():
            if letter in correct_positions.values():
                continue

            available_slots = [i for i in range(word_length) if word[i] == '' and i not in slots]
            if available_slots:
                chosen_slot = random.choice(available_slots)
                word[chosen_slot] = letter

        # Fill the remaining slots with randomized letters
        available_slots = [i for i in range(word_length) if word[i] == '']
        for slot in available_slots:
            word[slot] = random.choice(alphabet)

        generated_word = ''.join(word)
        word_list.append(generated_word)

    # return the expanded word bank
    return word_list


def solve_puzzle(mode, word_length, seed=None, custom_word=None):
    """
        the function of return the solution word for the puzzle
    """
    filtered_words = filter_words_bank_by_length(
        word_list=words_bank,
        word_length=word_length
    )

    # Create the word signals for filtering
    correct_positions = {}  # slot: correct letter
    present_letters = {}  # presented letter: the slots the letter is not in
    absent_letters = set()

    # set the max attempts to avoid the infinite loop
    attempts = 0
    max_attempts = 100

    while attempts < max_attempts:
        # Fallback mechanism: generate new words to word bank based on the constraints we collected
        if not filtered_words:
            print("Words bank is empty now. Generating more fallback words for guessing...")
            filtered_words = generate_random_words_with_constraints(
                word_length=word_length,
                correct_positions=correct_positions,
                present_letters=present_letters,
                absent_letters=absent_letters,
                num_words=1000
            )

        # retrieve the high entropy word
        guess = get_high_entropy_word(
            word_list=filtered_words,
            top_n=3
        )

        # Get the feedback from APU
        feedback_result = get_api_feedback(
            mode=mode,
            guess=guess,
            word_length=word_length,
            seed=seed,
            custom_word=custom_word
        )

        if feedback_result is None:
            print("Error retrieving the feedback from API. Stop guessing the word now.")
            return None

        attempts += 1
        print(f"Attempt {attempts}: Guess = {guess}, Feedback = {feedback_result}")

        # Check if all letters are correct in the feedback
        if all(item['result'] == 'correct' for item in feedback_result):
            final_word = guess
            print(f"Solved the word '{final_word}' in {attempts} attempts!")
            return final_word

        # Process feedback and update our word signals
        for item in feedback_result:
            if item['result'] == 'correct':
                correct_positions[item['slot']] = item['guess']
            elif item['result'] == 'present':
                if item['guess'] not in present_letters:
                    present_letters[item['guess']] = []
                present_letters[item['guess']].append(item['slot'])
            elif item['result'] == 'absent':
                absent_letters.add(item['guess'])

        # filtering the word bank by the word signal
        filtered_words = filter_words_bank_by_feedback(
            word_list=filtered_words,
            correct_positions=correct_positions,
            present_letters=present_letters,
            absent_letters=absent_letters
        )

    # if no solution is found within max attempts
    print(f"Could not solve the word within {max_attempts} attempts")
    return None


def print_welcome_logo():
    logo = """
 __        __         _                            _      
 \ \      / /__  _ __| | _____ _ __ ___   ___ _ __ | |_ ___
  \ \ /\ / / _ \| '__| |/ / _ \ '_ ` _ \ / _ \ '_ \| __/ __|
   \ V  V / (_) | |  |   <  __/ | | | | |  __/ | | | |_\__ \\
    \_/\_/ \___/|_|  |_|\_\___|_| |_| |_|\___|_| |_|\__|___/

                     Word Solver
    """
    print(logo)


def main():
    print("Welcome to Wordle Solver!")
    print_welcome_logo()

    while True:
        # Prompt user to select a play mode
        print("""
        Select a mode:
        1. Daily
        2. Random
        3. Custom Word
        4. Exit
        """)

        mode = input("Enter your choice (1-4): ").strip()

        if mode == '1':
            print("You selected Daily mode.")
            word_size_input = input("Enter the word size for the daily puzzle (default is 5): ").strip()
            word_size = int(word_size_input) if word_size_input else 5  # Default to 5 if input is empty
            seed = None
            custom_word = None
            mode_name = "daily"

        elif mode == '2':
            print("You selected Random mode.")
            word_size_input = input("Enter the word size for the random puzzle (default is 5): ").strip()
            word_size = int(word_size_input) if word_size_input else 5
            seed_input = input("Enter the seed for the random puzzle (default is 1234): ").strip()
            seed = int(seed_input) if seed_input else 1234
            custom_word = None
            mode_name = "random"

        elif mode == '3':
            print("You selected Custom Word mode.")
            custom_word_input = input("Enter the custom word to guess (default is 'alan') ").strip().lower()
            custom_word = custom_word_input if custom_word_input else 'alan'
            word_size = len(custom_word)
            seed = None
            mode_name = "custom"

        elif mode == '4':
            print("Exiting the game. Goodbye!")
            break

        else:
            print("Invalid choice. Please enter a number between 1 and 4.")
            continue

        # Run the puzzle solving function
        final_word = solve_puzzle(
            mode=mode_name,
            word_length=word_size,
            seed=seed,
            custom_word=custom_word
        )

        if final_word:
            print(f"Puzzle solved! The word is: {final_word}")
        else:
            print("Puzzle could not be solved..")

        play_again = input("Do you want to solve another puzzle? (yes/no): ").strip().lower()
        if play_again != 'yes':
            print("Goodbye~")
            break


if __name__ == "__main__":
    main()
