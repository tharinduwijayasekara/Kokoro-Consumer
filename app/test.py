import generate_audiobook

if __name__ == "__main__":
    text = generate_audiobook.fix_word_number_dash("Arthur-1 arthur 1 arthur - 1")
    print(f"Test completed successfully: {text}")