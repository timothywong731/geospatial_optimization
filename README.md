# Geospatial Optimization

This package provides tools and algorithms for optimizing the placement of stationary sensors in a geospatial area. It includes functionalities for defining operational areas, simulating sensor coverage, and visualizing the results.

## Installation

1.  Clone the repository:

    ```bash
    git clone https://github.com/timothywong731/geospatial_optimization.git
    cd geospatial_optimization
    ```

2.  Install the required dependencies using Poetry. If you don't have Poetry installed, follow the instructions [here](https://python-poetry.org/docs/#installation):

    ```bash
    poetry install
    ```

3.  Activate the virtual environment created by Poetry:

    ```bash
    poetry shell
    ```

## Usage

The main functionalities are available in the `geospatial_optimization` package. You can use the provided modules (`optimization.py`, `plotting.py`, `helpers.py`) in your Python scripts or interactive sessions.

### Example (using the demo notebook)

A demonstration of how to use the library is provided in the `demo.ipynb` Jupyter notebook. To run the demo:

1.  Make sure you have Jupyter installed within your Poetry environment (`poetry add jupyter`).
2.  Launch the Jupyter notebook server from within the activated Poetry shell:

    ```bash
    jupyter notebook
    ```

3.  Open the `demo.ipynb` file in your browser and run the cells.

### Key Modules:

-   `geospatial_optimization.optimization`: Contains the core optimization algorithms for sensor placement.
-   `geospatial_optimization.plotting`: Provides functions for visualizing operational areas, sensor placements, and coverage.
-   `geospatial_optimization.helpers`: Includes utility functions used across the project.
-   `geospatial_optimization.mobile_optimization`: Tools for selecting scanning
    positions and planning routes for moving sensors. See `mobile_demo.ipynb`
    for a short example.

