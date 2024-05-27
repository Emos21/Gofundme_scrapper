def remove_query_params(url):
    query_index = url.find("?")
    if query_index != -1:
        url = url[:query_index]
    return url

def clean_urls(input_file, output_file):
    # Open the input file for reading and output file for writing
    with open(input_file, 'r') as input_file, open(output_file, 'w') as output_file:
        # Read each line (URL) from the input file
        for line in input_file:
            # Remove leading and trailing whitespaces
            url = line.strip()
            # Clean the URL
            clean_url = remove_query_params(url)
            # Write the cleaned URL to the output file
            output_file.write(clean_url + '\n')

# Call the function with the input file and output file names
clean_urls('url.txt', 'clean_url.txt')
