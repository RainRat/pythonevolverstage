import pandas as pd
import matplotlib.pyplot as plt
import os
import argparse # Import argparse for command-line arguments

def plot_benchmark_progress(log_file='log.csv', output_image='progress.png'):
    """
    Reads a benchmark log file, processes the data, and generates a progress graph.

    The graph shows the percentage of the maximum possible score achieved
    at each generation, with vertical lines indicating changes in eras.
    """
    
    # Check if log file exists
    if not os.path.exists(log_file):
        print(f"Error: Log file '{log_file}' not found.")
        print("Please make sure the log file is in the same directory as the script.")
        print("A sample 'log.csv' was provided, but you may need to use your full log.")
        return

        print(f"Reading log file: {log_file}...")
    
    # --- Data Processing ---
    
    try:
        # Read the CSV log file into a pandas DataFrame
        df = pd.read_csv(log_file)
        
        # Ensure 'era', 'generation', and 'score' columns exist
        if not all(col in df.columns for col in ['era', 'generation', 'score']):
            print("Error: Log file must contain 'era', 'generation', and 'score' columns.")
            return

        # Define the maximum possible score per benchmark for each era.
        # Based on: Era 0 (1 battle * 3 pts/win), Era 1 (20 battles * 3 pts/win), Era 2 (100 battles * 3 pts/win)
        # We use the 0-indexed 'era' from your file.
        max_score_per_era = {
            0: 1 * 3,   # 1 battle, max 3 points
            1: 20 * 3,  # 20 battles, max 60 points
            2: 100 * 3  # 100 battles, max 300 points
        }
        
        print("Processing data...")
        
        # Group by 'era' and 'generation'
        # For each group, calculate the sum of 'score' and the count of benchmarks ('n_benchmarks')
        agg_data = df.groupby(['era', 'generation'])['score'].agg(['sum', 'count']).reset_index()
        agg_data.rename(columns={'sum': 'total_score', 'count': 'n_benchmarks'}, inplace=True)

        # Map the 'era' to its corresponding max score per benchmark
        agg_data['max_per_benchmark'] = agg_data['era'].map(max_score_per_era)

        # Handle potential new eras not defined in the map
        if agg_data['max_per_benchmark'].isnull().any():
            unknown_eras = agg_data[agg_data['max_per_benchmark'].isnull()]['era'].unique()
            print(f"Warning: Unknown eras found: {unknown_eras}.")
            print("Please update the 'max_score_per_era' dictionary in the script.")
            # Drop rows with unknown eras to avoid errors
            agg_data.dropna(subset=['max_per_benchmark'], inplace=True)

        # Calculate the total possible score for that generation's test run
        # (Number of benchmarks * max score for that era)
        agg_data['total_possible'] = agg_data['n_benchmarks'] * agg_data['max_per_benchmark']
        
        # Calculate the percentage of the max possible score
        agg_data['percentage'] = (agg_data['total_score'] / agg_data['total_possible']) * 100
        
        # Sort the data by generation to ensure the line plot is correct
        plot_data = agg_data.sort_values('generation').reset_index()
        
        # --- Handle empty data ---
        if plot_data.empty:
            print("No data to plot. Exiting.")
            return

        # --- Plotting ---

        print("Generating plot...")
        
        plt.figure(figsize=(15, 7))
        
        # Plot the main progress line
        plt.plot(plot_data['generation'], plot_data['percentage'], marker='o', linestyle='-', label='Benchmark Score %')
        
        # Find the generations where the era changes to draw vertical lines
        # We check where the 'era' value is different from the previous row
        era_change_indices = plot_data[plot_data['era'].diff() != 0].index
        
        # Get the corresponding generation values
        era_boundary_gens = plot_data.loc[era_change_indices, 'generation']
        
        # Draw a vertical line for each era change (except the very first one)
        for i, gen in enumerate(era_boundary_gens):
            if i == 0: continue # Skip the line for the start of the first era
            era_num = plot_data.loc[era_change_indices[i], 'era']
            plt.axvline(x=gen, color='red', linestyle='--', linewidth=1, 
                        label=f'Start of Era {era_num} (Gen {gen})')

        # --- Final Plot Styling ---
        
        plt.title('Benchmark Score Progress Over Generations', fontsize=16)
        plt.xlabel('Generation', fontsize=12)
        plt.ylabel('Score (% of Max Possible)', fontsize=12)
        
        # Set y-axis to be from 0% to 100%
        # MODIFICATION: Automatically adjust y-axis to fit data, starting from 0
        max_percentage = plot_data['percentage'].max()
        # Set top to 5% above max, or default to 100 if no data or max is 0
        top_limit = max_percentage * 1.05 if max_percentage > 0 else 100
        # Ensure the top limit is at least a small value if max_percentage is very low (but not 0)
        if 0 < max_percentage < 10 and top_limit < 10:
             top_limit = 10
        
        plt.ylim(0, top_limit)
        
        # Format x-axis to use full numbers instead of scientific notation
        plt.gca().get_xaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, p: format(int(x), ','))
        )
        
        plt.legend()
        plt.grid(True, linestyle=':', alpha=0.7)
        plt.tight_layout()
        
        # Save the plot to a file
        plt.savefig(output_image)
        plt.close()
        
        print(f"Success! Graph saved to {output_image}")

    except FileNotFoundError:
        # This catch is redundant with the os.path.exists check, but good practice
        print(f"Error: Could not find the file {log_file}.")
    except pd.errors.EmptyDataError:
        print(f"Error: The file {log_file} is empty.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # --- Command-Line Argument Parsing ---
    parser = argparse.ArgumentParser(
        description='Generate a progress plot from a benchmark log file.'
    )
    
    parser.add_argument(
        '-l', '--log_file',
        default='log.csv',
        help='The path to the input log file (default: log.csv)'
    )
    
    parser.add_argument(
        '-o', '--output_image',
        default='progress.png',
        help='The path to save the output graph image (default: progress.png)'
    )
    
    args = parser.parse_args()

    # Call the function with the parsed arguments
    plot_benchmark_progress(log_file=args.log_file, output_image=args.output_image)