package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
@Service class Entry {
    static class Sink { void required() {} }
    @Autowired Sink sink;
    public void run() { sink.required(); }
    public void parameter(Sink value) {}
}
