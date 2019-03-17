// Create a ES6 class component
class PeopleBookApp2 extends React.Component {
  render() {
    return (
      <div className="App">
        <div class="title">{this.props.name}</div>
        <div className="toc">
            {this.props.people.map(row => <a href={"#" + row.name} class="toc__person">
                <img src={row.photo} className="photo photo--small" />
                <div class="name name--brief">{row.name.split(' ')[0]}</div>
            </a>)}
        </div>
        <div class="people">
        {this.props.people.map(row => <div class="person" id={row.name}>
          <div class="name name--full">{row.name}</div>
          <img class="photo photo--large" src={row.photo} />
          <div class="label">Чем занимаюсь</div>
          <div class="answer">{row.occupation.split(/\n+/).map(paragraph => <div class="answer-chunk">{paragraph}</div>)}</div>
          <div class="label">О чем могу рассказать</div>
          <div class="answer">{row.knowledge}</div>
          <div class="label">Контакты</div>
          <div class="answer" dangerouslySetInnerHTML={{__html: myLinkify(row.profiles)}}></div>
          </div>)}
        </div>
      </div>
    );
  }
}