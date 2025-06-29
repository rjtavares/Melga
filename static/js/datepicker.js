document.addEventListener('DOMContentLoaded', function() {
    const datepickerInputs = document.querySelectorAll('.datepicker-input');

    datepickerInputs.forEach(input => {
        const calendar = input.nextElementSibling;

        input.addEventListener('focus', function() {
            renderCalendar(calendar, new Date(), this);
            calendar.style.display = 'block';
        });

        input.addEventListener('blur', function(e) {
            setTimeout(() => {
                if (!calendar.contains(document.activeElement)) {
                    calendar.style.display = 'none';
                }
            }, 0);
        });

        function renderCalendar(calendar, date, input) {
            calendar.innerHTML = '';

            const month = date.getMonth();
            const year = date.getFullYear();

            const header = document.createElement('div');
            header.classList.add('datepicker-header');

            const prevButton = document.createElement('button');
            prevButton.textContent = '<';
            prevButton.addEventListener('click', () => {
                renderCalendar(calendar, new Date(year, month - 1, 1), input);
            });

            const nextButton = document.createElement('button');
            nextButton.textContent = '>';
            nextButton.addEventListener('click', () => {
                renderCalendar(calendar, new Date(year, month + 1, 1), input);
            });

            const monthYear = document.createElement('span');
            monthYear.textContent = `${date.toLocaleString('default', { month: 'long' })} ${year}`;

            header.appendChild(prevButton);
            header.appendChild(monthYear);
            header.appendChild(nextButton);
            calendar.appendChild(header);

            const weekdaysContainer = document.createElement('div');
            weekdaysContainer.classList.add('datepicker-weekdays');
            const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            weekdays.forEach(weekday => {
                const day = document.createElement('div');
                day.textContent = weekday;
                weekdaysContainer.appendChild(day);
            });
            calendar.appendChild(weekdaysContainer);

            const daysContainer = document.createElement('div');
            daysContainer.classList.add('datepicker-days');

            const daysInMonth = new Date(year, month + 1, 0).getDate();

            for (let i = 1; i <= daysInMonth; i++) {
                const day = document.createElement('div');
                day.classList.add('datepicker-day');
                day.textContent = i;
                if (i === new Date().getDate() && month === new Date().getMonth() && year === new Date().getFullYear()) {
                    day.classList.add('today');
                }

                day.addEventListener('click', () => {
                    const selectedDate = new Date(year, month, i);
                    const yyyy = selectedDate.getFullYear();
                    const mm = String(selectedDate.getMonth() + 1).padStart(2, '0');
                    const dd = String(selectedDate.getDate()).padStart(2, '0');
                    input.value = `${yyyy}-${mm}-${dd}`;
                    calendar.style.display = 'none';
                });
                daysContainer.appendChild(day);
            }

            calendar.appendChild(daysContainer);
        }
    });
});